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
    ModelRefusalError,
    TaskEdge,
    TaskExecutionRound,
    TaskGraph,
    TaskNode,
    WorkerNodeResult,
    WorkerResult,
    classify_task,
    classify_task_with_model,
    decide_supervisor_step,
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
    assert graph.nodes[0].metadata["decision_check"] is True
    assert graph.nodes[1].metadata["decision_check"] is True
    assert graph.nodes[2].metadata["decision_check"] is True


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
    assert details["llm_attempts"][0]["response_type"] == "AIMessage"
    assert details["llm_attempts"][0]["content_preview"] == "not json"


@pytest.mark.asyncio
async def test_classify_task_with_model_retries_once_on_empty_output() -> None:
    class _Model:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content="")
            return AIMessage(
                content='{"task_type":"generic","confidence":0.88,"reason":"Quick informal check.","matched_signals":["不要正式写报告"]}'
            )

    model = _Model()
    classification, details = await classify_task_with_model(
        model=model,
        task="不要正式写报告，快速判断一下这个问题。",
    )

    assert model.calls == 2
    assert classification.primary_type == "generic"
    assert details["source"] == "llm_classifier"
    assert details["llm_attempts"][0]["content_is_empty"] is True
    assert details["llm_attempts"][1]["parsed_payload_found"] is True


@pytest.mark.asyncio
async def test_classify_task_with_model_raises_on_refusal() -> None:
    class _Model:
        async def ainvoke(self, _messages):
            return AIMessage(
                content="",
                response_metadata={
                    "model_name": "claude-sonnet-4-6",
                    "model_provider": "anthropic",
                    "stop_reason": "refusal",
                },
            )

    with pytest.raises(ModelRefusalError) as exc_info:
        await classify_task_with_model(
            model=_Model(),
            task="帮我做一个不允许的请求。",
        )

    assert exc_info.value.stage == "classifier"
    assert exc_info.value.user_message == "The model refused to answer this request."


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
    ]
    assert graph.nodes[0].metadata["planner_role"] == "generic_dynamic_graph_planner"
    assert graph.metadata["guidance_ids"] == ["generic_qa"]


def test_planner_uses_spawned_generic_subgraph() -> None:
    planner = HeuristicSupervisorPlanner()
    prior_round_graph = TaskGraph(
        graph_id="generic-r1",
        task_type="generic",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_generic",
                title="Plan generic graph",
                objective="plan",
                capability_bundles=["plan"],
            )
        ],
        edges=[],
    )
    prior_round = awaitable_round(
        graph=prior_round_graph,
        statuses={"init_generic": "completed"},
        spawned_subgraphs={
            "init_generic": {
                "nodes": [
                    {
                        "node_id": "source_context",
                        "title": "Source context",
                        "objective": "Gather source evidence.",
                        "capability_bundles": ["web_search", "web_fetch", "validate"],
                    },
                    {
                        "node_id": "local_context",
                        "title": "Local context",
                        "objective": "Inspect local evidence.",
                        "capability_bundles": ["repo_fetch", "db_access", "validate"],
                    },
                    {
                        "node_id": "synthesize_answer",
                        "title": "Synthesize answer",
                        "objective": "Compare evidence and answer.",
                        "capability_bundles": ["summarize", "validate"],
                    },
                    {
                        "node_id": "summarize",
                        "title": "Summarize",
                        "objective": "Summarize final result.",
                        "capability_bundles": ["summarize"],
                    },
                ],
                "edges": [
                    {"source": "source_context", "target": "synthesize_answer"},
                    {"source": "local_context", "target": "synthesize_answer"},
                    {"source": "synthesize_answer", "target": "summarize"},
                ],
            }
        },
    )

    graph = planner.plan_round(
        task="最近两周国内新冠和流感大概是什么态势？先给我一个口头判断，不要正式写作。",
        retrieved_cases=[],
        prior_rounds=[prior_round],
    )

    assert graph.task_type == "generic"
    assert [node.node_id for node in graph.nodes] == [
        "source_context",
        "local_context",
        "synthesize_answer",
        "summarize",
    ]
    assert {(edge.source, edge.target) for edge in graph.edges} == {
        ("source_context", "synthesize_answer"),
        ("local_context", "synthesize_answer"),
        ("synthesize_answer", "summarize"),
    }
    assert graph.metadata["planner_generated"] is True


def test_planner_connects_spawned_generic_terminal_nodes_to_summarize() -> None:
    planner = HeuristicSupervisorPlanner()
    prior_round_graph = TaskGraph(
        graph_id="generic-r1",
        task_type="generic",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_generic",
                title="Plan generic graph",
                objective="plan",
                capability_bundles=["plan"],
            )
        ],
        edges=[],
    )
    prior_round = awaitable_round(
        graph=prior_round_graph,
        statuses={"init_generic": "completed"},
        spawned_subgraphs={
            "init_generic": {
                "nodes": [
                    {
                        "node_id": "validate_csv_inputs",
                        "title": "Validate CSV inputs",
                        "objective": "Find and validate local CSV logs.",
                        "capability_bundles": ["validate", "data_filter"],
                    },
                    {
                        "node_id": "analyze_data",
                        "title": "Analyze data",
                        "objective": "Analyze error rate changes.",
                        "capability_bundles": ["metric_compute", "data_filter"],
                    },
                ],
                "edges": [
                    {"source": "validate_csv_inputs", "target": "analyze_data"},
                ],
            }
        },
    )

    graph = planner.plan_round(
        task="请根据本地 CSV 日志判断最近一周错误率上升的主要原因，并给一个处置建议。",
        retrieved_cases=[],
        prior_rounds=[prior_round],
    )

    assert [node.node_id for node in graph.nodes] == [
        "validate_csv_inputs",
        "analyze_data",
        "summarize",
    ]
    assert ("analyze_data", "summarize") in {
        (edge.source, edge.target) for edge in graph.edges
    }


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
    assert classification.guidance_ids == ["generic_qa"]


@pytest.mark.asyncio
async def test_classify_task_with_model_generic_attaches_generic_qa_guidance() -> None:
    class _Model:
        async def ainvoke(self, _messages):
            return AIMessage(
                content='{"task_type":"generic","confidence":0.92,"reason":"Direct local-code explanation request.","matched_signals":["只基于本地代码","简短结论"]}'
            )

    classification, details = await classify_task_with_model(
        model=_Model(),
        task="请只基于本地代码，给我一个简短结论：generic harness 现在是真的在做 skill 进化了吗？",
    )

    assert classification.primary_type == "generic"
    assert classification.guidance_ids == ["generic_qa"]
    assert details["guidance_ids"] == ["generic_qa"]


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
    ]
    assert graph.nodes[0].capability_bundles == ["plan", "task_manage", "validate"]
    assert graph.nodes[0].metadata["planner_role"] == "report_dynamic_lane_planner"
    assert "spawned_subgraph" in graph.nodes[0].objective


def test_planner_creates_dynamic_report_lane_graph_from_init_result() -> None:
    planner = HeuristicSupervisorPlanner()
    first_graph = planner.plan_round(
        task="请写一份 XFG.1.1 风险评估报告，需要监测数据、本地历史数据、本地算子计算增长率、文献证据。",
        retrieved_cases=[],
        prior_rounds=[],
    )
    first_round = TaskExecutionRound(
        graph=first_graph,
        node_results=[
            WorkerNodeResult(
                node_id="init_report",
                status="completed",
                summary="report contract initialized",
                artifacts=["report_contract.md"],
                spawned_subgraph={
                    "nodes": [
                        {
                            "node_id": "monitoring_lane_global",
                            "title": "Global monitoring",
                            "objective": "Collect global surveillance evidence.",
                            "capability_bundles": ["web_search", "web_fetch", "validate"],
                        },
                        {
                            "node_id": "existing_data_lane_history",
                            "title": "History store",
                            "objective": "Query reusable local history records.",
                            "capability_bundles": ["db_access", "api_call", "data_filter", "validate"],
                        },
                        {
                            "node_id": "computed_data_lane_growth",
                            "title": "Growth computation",
                            "objective": "Run a local operator to compute growth rate if existing data is insufficient.",
                            "capability_bundles": ["operator_filter", "data_filter", "metric_compute", "wdl_run", "validate"],
                        },
                        {
                            "node_id": "literature_lane_escape",
                            "title": "Immune escape literature",
                            "objective": "Collect literature evidence.",
                            "capability_bundles": ["web_search", "web_fetch", "api_call", "validate"],
                        },
                    ],
                    "edges": [
                        {"from": "monitoring_lane_global", "to": "compose_report"},
                        {"source": "existing_data_lane_history", "target": "compose_report"},
                        {"source": "computed_data_lane_growth", "target": "compose_report"},
                        {"source": "literature_lane_escape", "target": "compose_report"},
                        {"source": "compose_report", "target": "summarize"},
                    ],
                },
            )
        ],
    )

    graph = planner.plan_round(
        task="请写一份 XFG.1.1 风险评估报告，需要监测数据、本地历史数据、本地算子计算增长率、文献证据。",
        retrieved_cases=[],
        prior_rounds=[first_round],
    )

    assert [node.node_id for node in graph.nodes] == [
        "monitoring_lane_global",
        "existing_data_lane_history",
        "computed_data_lane_growth",
        "literature_lane_escape",
        "compose_report",
        "summarize",
    ]
    assert graph.nodes[1].metadata["report_lane_base"] == "existing_data_lane"
    assert graph.nodes[2].metadata["report_lane_base"] == "computed_data_lane"
    assert graph.nodes[2].capability_bundles == [
        "operator_filter",
        "data_filter",
        "metric_compute",
        "wdl_run",
        "validate",
    ]


def test_dynamic_report_lane_graph_caps_lane_counts() -> None:
    planner = HeuristicSupervisorPlanner()
    first_graph = planner.plan_round(
        task="请写一份复杂报告。",
        retrieved_cases=[],
        prior_rounds=[],
    )
    requested_nodes = [
        {
            "node_id": f"computed_data_lane_metric_{index}",
            "title": f"Metric {index}",
            "objective": "Compute a metric.",
            "capability_bundles": ["operator_filter", "metric_compute", "validate"],
        }
        for index in range(1, 6)
    ] + [
        {
            "node_id": f"monitoring_lane_region_{index}",
            "title": f"Region {index}",
            "objective": "Collect monitoring evidence.",
            "capability_bundles": ["web_search", "web_fetch", "validate"],
        }
        for index in range(1, 6)
    ]
    first_round = TaskExecutionRound(
        graph=first_graph,
        node_results=[
            WorkerNodeResult(
                node_id="init_report",
                status="completed",
                summary="report contract initialized",
                artifacts=["report_contract.md"],
                spawned_subgraph={"nodes": requested_nodes, "edges": []},
            )
        ],
    )

    graph = planner.plan_round(
        task="请写一份复杂报告。",
        retrieved_cases=[],
        prior_rounds=[first_round],
    )

    evidence_nodes = [
        node for node in graph.nodes if node.node_id not in {"compose_report", "summarize"}
    ]
    assert len(evidence_nodes) == 6
    assert sum(node.metadata["report_lane_base"] == "computed_data_lane" for node in evidence_nodes) == 3
    assert sum(node.metadata["report_lane_base"] == "monitoring_lane" for node in evidence_nodes) == 3


@pytest.mark.asyncio
async def test_init_report_without_shape_declared_finalizes_node_decision(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-report-shape-missing"
    (run_dir / "report_init").mkdir(parents=True)
    (run_dir / "report_init" / "report_contract.json").write_text(
        json.dumps(
            {
                "language": "zh-CN",
                "tone": "formal",
                "citation_style": "numbered",
            }
        ),
        encoding="utf-8",
    )
    graph = TaskGraph(
        graph_id="graph-report-shape-missing",
        task_type="report",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_report",
                title="Initialize report",
                objective="plan report graph",
                capability_bundles=["plan", "task_manage", "validate"],
                metadata={"decision_check": True, "run_dir": str(run_dir)},
            ),
            TaskNode(
                node_id="summarize",
                title="Summarize",
                objective="summarize outcome",
                capability_bundles=["summarize"],
            ),
        ],
        edges=[TaskEdge(source="init_report", target="summarize")],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "init_report":
            return WorkerResult(
                status="completed",
                summary="report contract initialized",
                artifacts=["report_init/report_contract.json"],
                spawned_subgraph={
                    "nodes": [
                        {
                            "node_id": "monitoring_lane",
                            "title": "Monitoring lane",
                            "objective": "Collect monitoring evidence.",
                            "capability_bundles": ["web_search", "web_fetch", "validate"],
                        }
                    ],
                    "edges": [],
                },
            )
        raise AssertionError("summarize should not run after a finalizing init_report decision")

    result = await execute_graph_round(graph, worker_runner)
    decision = decide_supervisor_step(result)

    by_node = {item.node_id: item for item in result.node_results}
    assert by_node["check_init_report"].status == "partial"
    assert "did not declare a report shape" in by_node["check_init_report"].summary
    assert by_node["summarize"].status == "blocked"
    assert decision.decision == "stop"
    assert decision.reason == "Node decision check requested finalization."
    assert decision.failed_nodes == ["init_report"]


@pytest.mark.asyncio
async def test_init_report_with_shape_declared_passes_node_decision(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-report-shape-present"
    (run_dir / "report_init").mkdir(parents=True)
    (run_dir / "report_init" / "report_contract.json").write_text(
        json.dumps(
            {
                "shape_archetype": "WHO-style risk assessment",
                "required_sections_outline": [
                    "## Current Assessment",
                    "## Evidence",
                ],
            }
        ),
        encoding="utf-8",
    )
    graph = TaskGraph(
        graph_id="graph-report-shape-present",
        task_type="report",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_report",
                title="Initialize report",
                objective="plan report graph",
                capability_bundles=["plan", "task_manage", "validate"],
                metadata={"decision_check": True, "run_dir": str(run_dir)},
            )
        ],
        edges=[],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        return WorkerResult(
            status="completed",
            summary="report contract initialized",
            artifacts=["report_init/report_contract.json"],
            spawned_subgraph={
                "nodes": [
                    {
                        "node_id": "monitoring_lane",
                        "title": "Monitoring lane",
                        "objective": "Collect monitoring evidence.",
                        "capability_bundles": ["web_search", "web_fetch", "validate"],
                    }
                ],
                "edges": [],
            },
        )

    result = await execute_graph_round(graph, worker_runner)
    decision = decide_supervisor_step(result)

    by_node = {item.node_id: item for item in result.node_results}
    assert by_node["init_report"].status == "completed"
    assert "check_init_report" not in by_node
    assert decision.decision == "stop"
    assert decision.reason == "All nodes completed."
    assert decision.failed_nodes == []


@pytest.mark.asyncio
async def test_init_report_with_archetype_synonyms_passes_node_decision(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-report-archetype-synonym"
    (run_dir / "report_init").mkdir(parents=True)
    (run_dir / "report_init" / "report_contract.json").write_text(
        json.dumps(
            {
                "primary_archetype": "WHO-style risk assessment",
                "report_shape_notes": [
                    "Use the user-requested section order.",
                    "Use numbered Markdown major sections.",
                ],
            }
        ),
        encoding="utf-8",
    )
    graph = TaskGraph(
        graph_id="graph-report-archetype-synonym",
        task_type="report",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_report",
                title="Initialize report",
                objective="plan report graph",
                capability_bundles=["plan", "task_manage", "validate"],
                metadata={"decision_check": True, "run_dir": str(run_dir)},
            )
        ],
        edges=[],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        return WorkerResult(
            status="completed",
            summary="report contract initialized",
            artifacts=["report_init/report_contract.json"],
            spawned_subgraph={
                "nodes": [
                    {
                        "node_id": "monitoring_lane",
                        "title": "Monitoring lane",
                        "objective": "Collect monitoring evidence.",
                        "capability_bundles": ["web_search", "web_fetch", "validate"],
                    }
                ],
                "edges": [],
            },
        )

    result = await execute_graph_round(graph, worker_runner)
    decision = decide_supervisor_step(result)

    by_node = {item.node_id: item for item in result.node_results}
    assert by_node["init_report"].status == "completed"
    assert "check_init_report" not in by_node
    assert decision.decision == "stop"
    assert decision.failed_nodes == []


def test_planner_excludes_explicitly_forbidden_benchmark_tools() -> None:
    planner = HeuristicSupervisorPlanner()
    benchmark_root = Path.cwd() / "workspace" / "test-benchmark-catalog-exclude"
    benchmark_root.mkdir(parents=True, exist_ok=True)

    graph = planner.plan_round(
        task=(
            f"请在 {benchmark_root} 里挑选共享数据集并选择多个算子并行跑。"
            "不要选 spades 和 megahit。"
        ),
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "benchmark"
    assert graph.nodes[0].metadata["selected_tools"] == []
    assert sorted(graph.nodes[0].metadata["excluded_tools"]) == ["megahit", "spades"]


def test_planner_detects_benchmark_root_from_task_path() -> None:
    planner = HeuristicSupervisorPlanner()
    benchmark_root = Path.cwd() / "workspace" / "test-benchmark-catalog"
    benchmark_root.mkdir(parents=True, exist_ok=True)

    graph = planner.plan_round(
        task=(
            f"我想评估 {benchmark_root} 里的 short-read-ecoli-srr001666 数据集在不同组装工具上的表现。"
            "请你自己决定应该跑哪些合适的工具，最后比较 contig_count、assembly_size、n50。"
        ),
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "benchmark"
    assert [node.node_id for node in graph.nodes] == ["register"]
    assert graph.nodes[0].metadata["selected_tools"] == []
    assert graph.nodes[0].metadata["benchmark_root"] == str(benchmark_root.resolve())


def test_planner_keeps_register_shape_for_benchmark_asset_paths(tmp_path: Path) -> None:
    planner = HeuristicSupervisorPlanner()
    benchmark_root = tmp_path / "arbitrary-benchmark-assets"
    canu_dir = benchmark_root / "新冠病毒组装" / "002_canu"
    flye_dir = benchmark_root / "新冠病毒组装" / "004_Flye"
    canu_dir.mkdir(parents=True)
    flye_dir.mkdir(parents=True)
    (canu_dir / "inputs.json").write_text(
        json.dumps({"CanuWorkflow.reads_fastq": "results/real-tests/canu/pacbio.fastq"}),
        encoding="utf-8",
    )
    (flye_dir / "inputs.json").write_text(
        json.dumps({"FlyeAssembly.reads": "results/real-tests/canu/pacbio.fastq"}),
        encoding="utf-8",
    )
    (canu_dir / "canu.wdl").write_text('workflow CanuWorkflow {}\nruntime { docker: "benchmark/canu:test" }\n', encoding="utf-8")
    (flye_dir / "flye.wdl").write_text('workflow FlyeAssembly {}\nruntime { docker: "benchmark/flye:test" }\n', encoding="utf-8")

    graph = planner.plan_round(
        task=(
            f"下面这个路径中有几个病毒组装算子的数据集和wdl文件：{benchmark_root}。"
            "挑选共享数据集并挑选多个算子并行跑，然后分析总结。不要选spades和megahit。"
        ),
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "benchmark"
    assert graph.nodes[0].metadata["selected_tools"] == []
    assert graph.nodes[0].metadata["excluded_tools"] == []


def test_planner_keeps_register_shape_for_family_hint_paths(
    tmp_path: Path,
) -> None:
    planner = HeuristicSupervisorPlanner()
    benchmark_root = tmp_path / "benchmark"
    acvalidator_dir = benchmark_root / "circrna" / "ACValidator"
    autocirc_dir = benchmark_root / "circrna" / "AutoCirc"
    acvalidator_dir.mkdir(parents=True)
    autocirc_dir.mkdir(parents=True)
    (acvalidator_dir / "input.json").write_text(
        json.dumps({"ACValidatorWorkflow.reference_fasta": "/old/acvalidator/ref.fa"}),
        encoding="utf-8",
    )
    (autocirc_dir / "input.json").write_text(
        json.dumps({"AutoCircWorkflow.reference_genome": "/old/autocirc/chr22.fa"}),
        encoding="utf-8",
    )
    (acvalidator_dir / "workflow.wdl").write_text(
        'workflow ACValidatorWorkflow {}\nruntime { docker: "benchmark/acvalidator:test" }\n',
        encoding="utf-8",
    )
    (autocirc_dir / "workflow.wdl").write_text(
        'workflow AutoCircWorkflow {}\nruntime { docker: "benchmark/autocirc:test" }\n',
        encoding="utf-8",
    )

    graph = planner.plan_round(
        task=(
            f"下面这个路径中有几个circRNA算子的数据集和wdl文件：{benchmark_root / 'circrna'}\n"
            f"{benchmark_root / 'datasets'}\n"
            "你需要挑选共享数据集并挑选多个算子，并行跑算子，然后对结果进行分析，总结"
        ),
        retrieved_cases=[],
        prior_rounds=[],
    )

    assert graph.task_type == "benchmark"
    assert graph.nodes[0].metadata["selected_tools"] == []


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


def test_planner_expands_benchmark_workers_after_partial_register_with_ready_tools() -> None:
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
        statuses={"register": "partial"},
        spawned_subgraphs={
            "register": {
                "selected_tools": ["ACValidator", "AutoCirc"],
                "blocked_tools": ["AQUARIUM-HB"],
            }
        },
    )

    graph = planner.plan_round(
        task="我想评估 circRNA benchmark 数据集在不同工具上的表现。",
        retrieved_cases=[],
        prior_rounds=[prior_round],
    )

    assert [node.node_id for node in graph.nodes] == [
        "ACValidator",
        "AutoCirc",
        "summarize",
    ]


def test_planner_summarizes_when_partial_register_has_only_blocked_tools() -> None:
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
        statuses={"register": "partial"},
        spawned_subgraphs={
            "register": {
                "selected_tools": [],
                "registered_tools": ["ACValidator", "AutoCirc"],
                "blocked_tools": ["ACValidator", "AutoCirc"],
            }
        },
    )

    graph = planner.plan_round(
        task="我想评估 circRNA benchmark 数据集在不同工具上的表现。",
        retrieved_cases=[],
        prior_rounds=[prior_round],
    )

    assert [node.node_id for node in graph.nodes] == ["summarize"]

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
async def test_execute_graph_round_allows_partial_dependencies_to_continue() -> None:
    graph = TaskGraph(
        graph_id="graph-partial",
        task_type="benchmark",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="canu",
                title="Run canu",
                objective="execute canu",
                capability_bundles=["docker_build_run"],
            ),
            TaskNode(
                node_id="Flye",
                title="Run Flye",
                objective="execute flye",
                capability_bundles=["docker_build_run"],
            ),
            TaskNode(
                node_id="summarize",
                title="Summarize",
                objective="summarize partial results",
                capability_bundles=["summarize"],
            ),
        ],
        edges=[
            TaskEdge(source="canu", target="summarize"),
            TaskEdge(source="Flye", target="summarize"),
        ],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "canu":
            return WorkerResult(status="partial", summary="canu partial")
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await execute_graph_round(graph, worker_runner)

    by_node = {item.node_id: item for item in result.node_results}
    assert by_node["canu"].status == "partial"
    assert by_node["Flye"].status == "completed"
    assert by_node["summarize"].status == "completed"


@pytest.mark.asyncio
async def test_execute_graph_round_stops_after_node_decision_check() -> None:
    graph = TaskGraph(
        graph_id="graph-decision-stop",
        task_type="github2workspace",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="inspect",
                title="Inspect",
                objective="inspect repo",
                capability_bundles=["repo_fetch"],
                metadata={"decision_check": True},
            ),
            TaskNode(
                node_id="summarize",
                title="Summarize",
                objective="summarize outcome",
                capability_bundles=["summarize"],
            ),
        ],
        edges=[TaskEdge(source="inspect", target="summarize")],
    )
    seen: list[str] = []

    async def worker_runner(node: TaskNode) -> WorkerResult:
        seen.append(node.node_id)
        if node.node_id == "inspect":
            return WorkerResult(
                status="failed",
                summary="inspect failed",
                failure_reason="network",
            )
        raise AssertionError("summarize should not run after a finalizing node decision check")

    result = await execute_graph_round(graph, worker_runner)
    decision = decide_supervisor_step(result)

    by_node = {item.node_id: item for item in result.node_results}
    assert seen == ["inspect"]
    assert by_node["inspect"].status == "failed"
    assert by_node["check_inspect"].status == "partial"
    assert by_node["summarize"].status == "blocked"
    assert by_node["summarize"].failure_reason == "blocked_by_node_decision_check"
    assert decision.decision == "stop"
    assert decision.reason == "Node decision check requested finalization."
    assert decision.failed_nodes == ["inspect"]


@pytest.mark.asyncio
async def test_node_decision_check_allows_fallback_for_unusable_generic_plan() -> None:
    graph = TaskGraph(
        graph_id="graph-decision-check",
        task_type="generic",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="init_generic",
                title="Plan generic graph",
                objective="plan",
                capability_bundles=["plan", "validate"],
                metadata={"decision_check": True},
            )
        ],
        edges=[],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        return WorkerResult(
            status="completed",
            summary="I finished, but forgot to return spawned_subgraph.",
        )

    result = await execute_graph_round(graph, worker_runner)
    decision = decide_supervisor_step(result)

    by_node = {item.node_id: item for item in result.node_results}
    assert by_node["init_generic"].status == "completed"
    assert decision.decision == "stop"
    assert decision.reason == "All nodes completed."
    assert "check_init_generic" not in by_node
    assert decision.failed_nodes == []


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
