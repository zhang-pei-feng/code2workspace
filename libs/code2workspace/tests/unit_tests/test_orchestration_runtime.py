"""Unit tests for the supervisor graph runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.errors import GraphInterrupt

from code2workspace.orchestration_runtime import (
    CaseTraceRecord,
    HeuristicSupervisorPlanner,
    TaskEdge,
    TaskGraph,
    TaskNode,
    WorkerResult,
    classify_task,
    classify_task_with_model,
    execute_graph_round,
)


def test_planner_creates_github2workspace_graph() -> None:
    planner = HeuristicSupervisorPlanner()

    graph = planner.plan_round(
        task=(
            "基于仓库中涉及的真实测试数据和任务脚本信息，完成仓库镜像的构建与基础验证；"
            "仓库地址：https://github.com/ablab/spades"
        ),
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "github2workspace"
    assert [node.node_id for node in graph.nodes] == [
        "inspect",
        "build",
        "wdl",
        "summarize",
    ]
    assert graph.nodes[0].capability_bundles == ["repo_fetch", "validate"]
    assert graph.nodes[1].capability_bundles == ["docker_build_run", "validate"]
    assert graph.nodes[2].capability_bundles == ["wdl_run", "validate"]
    assert graph.nodes[3].capability_bundles == ["summarize"]


@pytest.mark.asyncio
async def test_classify_task_with_model_uses_llm_when_confident() -> None:
    class _Model:
        async def ainvoke(self, _messages):
            return AIMessage(
                content='{"task_type":"report","confidence":0.91,"reason":"Formal risk assessment request.","matched_signals":["风险评估","WHO 风格"]}'
            )

    classification, details = await classify_task_with_model(
        model=_Model(),
        task="请按 WHO 风格写一份 XFG.1.1 毒株风险评估报告。",
    )

    assert classification.primary_type == "report"
    assert details["source"] == "llm_classifier"
    assert details["confidence"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_classify_task_with_model_falls_back_to_rules_on_invalid_output() -> None:
    class _Model:
        async def ainvoke(self, _messages):
            return AIMessage(content="not json")

    classification, details = await classify_task_with_model(
        model=_Model(),
        task="基于仓库中涉及的真实测试数据和任务脚本信息，仓库地址：https://github.com/ablab/spades",
    )

    assert classification.primary_type == "github2workspace"
    assert details["source"] == "rules_fallback"
    assert details["llm_error"] == "invalid_classifier_output"


def test_planner_creates_generic_graph_for_unknown_task() -> None:
    planner = HeuristicSupervisorPlanner()

    graph = planner.plan_round(
        task="帮我整理这个任务的执行思路并给出下一步建议。",
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "generic"
    assert [node.node_id for node in graph.nodes] == [
        "init_generic",
        "worker_context",
        "worker_solution",
        "compose_generic",
        "summarize",
    ]
    assert graph.metadata["guidance_ids"] == []


def test_planner_retries_analyze_when_initial_analysis_failed() -> None:
    planner = HeuristicSupervisorPlanner()
    prior_round_graph = TaskGraph(
        graph_id="generic-r1",
        task_type="generic",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_generic",
                title="Initialize generic run",
                objective="init",
                capability_bundles=["plan"],
            )
        ],
        edges=[],
    )
    prior_round = awaitable_round(
        graph=prior_round_graph,
        statuses={"init_generic": "failed"},
    )

    graph = planner.plan_round(
        task="帮我整理这个任务的执行思路并给出下一步建议。",
        retrieved_cases=[],
        prior_rounds=[prior_round],
    )

    assert [node.node_id for node in graph.nodes] == [
        "retry_init_generic",
        "compose_generic",
        "summarize",
    ]


def test_rule_classifier_keeps_oral_judgment_request_generic() -> None:
    classification = classify_task(
        "最近两周国内新冠和流感大概是什么态势？先给我一个口头判断，不要正式写作。"
    )

    assert classification.primary_type == "generic"


def test_planner_creates_report_graph() -> None:
    planner = HeuristicSupervisorPlanner()

    graph = planner.plan_round(
        task="请按 WHO 风格写一份 XFG.1.1 毒株风险评估报告，至少覆盖相对增长速率、临床重症率风险、免疫逃逸能力。",
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "report"
    assert [node.node_id for node in graph.nodes] == [
        "init_report",
        "monitoring_lane",
        "local_data_lane",
        "literature_lane",
        "compose_report",
        "summarize",
    ]
    assert graph.nodes[0].capability_bundles == ["plan", "task_manage", "validate"]
    assert graph.nodes[1].capability_bundles == ["web_search", "web_fetch", "validate"]
    assert graph.nodes[2].capability_bundles == ["db_access", "api_call", "validate"]
    assert graph.nodes[3].capability_bundles == ["web_search", "web_fetch", "api_call"]
    assert graph.nodes[4].capability_bundles == ["summarize", "validate"]


def test_planner_selects_benchmark_tools_from_catalog_dataset() -> None:
    planner = HeuristicSupervisorPlanner()
    benchmark_root = Path.cwd() / "workspace" / "test-benchmark-catalog"
    catalog_path = benchmark_root / "datasets" / "benchmark_catalog.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_key = "short-read-ecoli-srr001666"
    expected_tools = ["assembler-a", "assembler-b"]
    catalog_path.write_text(
        json.dumps(
            {
                "datasets": {
                    dataset_key: {
                        "dataset_id": "SRR001666",
                        "description": "short read fixture",
                        "shared_between": expected_tools,
                    }
                },
                "repo_cases": {
                    "assembler-a": {"dataset_key": dataset_key},
                    "assembler-b": {"dataset_key": dataset_key},
                },
            }
        ),
        encoding="utf-8",
    )

    graph = planner.plan_round(
        task=(
            f"我想评估 {benchmark_root} 里的 {dataset_key} 数据集在不同组装工具上的表现。"
            "请你自己决定应该跑哪些合适的工具，最后比较 contig_count、assembly_size、n50。"
        ),
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "benchmark"
    assert [node.node_id for node in graph.nodes] == ["register"]
    assert graph.nodes[0].metadata["selected_tools"] == expected_tools


def test_planner_expands_benchmark_workers_after_register_selects_tools() -> None:
    planner = HeuristicSupervisorPlanner()
    prior_round_graph = TaskGraph(
        graph_id="benchmark-r1",
        task_type="benchmark",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="register",
                title="Register",
                objective="register",
                capability_bundles=["plan", "task_manage", "validate"],
            )
        ],
        edges=[],
    )
    prior_round = awaitable_round(
        graph=prior_round_graph,
        statuses={"register": "completed"},
        spawned_subgraphs={"register": {"selected_tools": ["canu", "Flye"]}},
    )

    graph = planner.plan_round(
        task="我想评估 long-read-ecoli-pacbio benchmark 数据集在不同组装工具上的表现。",
        retrieved_cases=[],
        prior_rounds=[prior_round],
    )

    assert [node.node_id for node in graph.nodes] == ["canu", "Flye", "summarize"]


@pytest.mark.asyncio
async def test_execute_graph_round_marks_failed_dependencies_blocked() -> None:
    graph = TaskGraph(
        graph_id="graph-1",
        task_type="github2workspace",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="inspect",
                title="Inspect",
                objective="inspect repo",
                capability_bundles=["repo_fetch"],
            ),
            TaskNode(
                node_id="build",
                title="Build",
                objective="build image",
                capability_bundles=["docker_build_run"],
            ),
        ],
        edges=[TaskEdge(source="inspect", target="build")],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "inspect":
            return WorkerResult(
                status="failed",
                summary="inspect failed",
                failure_reason="network",
            )
        raise AssertionError("blocked node should not run")

    result = await execute_graph_round(graph, worker_runner)

    by_node = {item.node_id: item for item in result.node_results}
    assert by_node["inspect"].status == "failed"
    assert by_node["build"].status == "blocked"
    assert by_node["build"].failure_reason == "blocked_by_failed_dependency"


@pytest.mark.asyncio
async def test_execute_graph_round_runs_parallel_ready_nodes() -> None:
    graph = TaskGraph(
        graph_id="graph-2",
        task_type="benchmark",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="spades",
                title="SPAdes",
                objective="run spades",
                capability_bundles=["docker_build_run"],
            ),
            TaskNode(
                node_id="megahit",
                title="MEGAHIT",
                objective="run megahit",
                capability_bundles=["docker_build_run"],
            ),
        ],
        edges=[],
    )
    seen: list[str] = []

    async def worker_runner(node: TaskNode) -> WorkerResult:
        seen.append(node.node_id)
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await execute_graph_round(graph, worker_runner)

    assert set(seen) == {"spades", "megahit"}
    assert result.completed_count == 2


@pytest.mark.asyncio
async def test_execute_graph_round_reraises_langgraph_interrupts() -> None:
    graph = TaskGraph(
        graph_id="graph-interrupt",
        task_type="generic",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="execute_task",
                title="Execute",
                objective="ask user",
                capability_bundles=["validate"],
            ),
        ],
        edges=[],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        await execute_graph_round(graph, worker_runner)


def test_planner_builds_benchmark_replan_graph_from_failed_nodes() -> None:
    planner = HeuristicSupervisorPlanner()
    prior_round_graph = TaskGraph(
        graph_id="bench-r1",
        task_type="benchmark",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="register",
                title="Register",
                objective="register",
                capability_bundles=["task_manage"],
            ),
            TaskNode(
                node_id="spades",
                title="SPAdes",
                objective="spades",
                capability_bundles=["docker_build_run"],
            ),
            TaskNode(
                node_id="megahit",
                title="MEGAHIT",
                objective="megahit",
                capability_bundles=["docker_build_run"],
            ),
        ],
        edges=[],
    )
    prior_round = awaitable_round(
        graph=prior_round_graph,
        statuses={
            "register": "completed",
            "spades": "completed",
            "megahit": "failed",
        },
    )

    graph = planner.plan_round(
        task="先使用共享数据集运行这 7 个本地新冠组装 benchmark case，并分层记录各 case 的完成情况。",
        retrieved_cases=[CaseTraceRecord(task_type="benchmark", summary="old bench")],
        prior_rounds=[prior_round],
    )

    assert graph.round_index == 2
    assert [node.node_id for node in graph.nodes] == ["retry_megahit", "summarize"]


def awaitable_round(
    *,
    graph: TaskGraph,
    statuses: dict[str, str],
    spawned_subgraphs: dict[str, dict[str, object]] | None = None,
):
    """Build a lightweight prior round object for planner tests."""

    from code2workspace.orchestration_runtime import TaskExecutionRound, WorkerNodeResult

    return TaskExecutionRound(
        graph=graph,
        node_results=[
            WorkerNodeResult(
                node_id=node_id,
                status=status,
                summary=status,
                spawned_subgraph=(spawned_subgraphs or {}).get(node_id),
            )
            for node_id, status in statuses.items()
        ],
    )
