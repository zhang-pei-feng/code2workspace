"""Tests for the CLI supervisor runtime."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.errors import GraphInterrupt

import code2workspace.orchestration_runtime as orchestration_runtime
import code2workspace_cli.supervisor_runtime as supervisor_runtime
from code2workspace.orchestration_runtime import (
    ModelRefusalError,
    SupervisorDecision,
    TaskGraph,
    TaskNode,
    WorkerResult,
    classify_task_with_model,
    execute_graph_round,
)
from code2workspace_cli.agent import create_cli_agent
from code2workspace_cli.benchmark_result_store import (
    BenchmarkResultSearchFilter,
    BenchmarkResultStore,
)
from code2workspace_cli.operator_store import OperatorSearchFilter, OperatorStore
from code2workspace_cli.supervisor_runtime import (
    _build_worker_invoke_request,
    _build_benchmark_comparison,
    _build_worker_prompt,
    _github2workspace_product_status,
    _invoke_worker_agent,
    _latest_human_route_mode,
    _last_ai_text,
    _parse_worker_result,
    _run_worker_and_capture,
    SQLiteCaseIndex,
    SupervisorWorkerRunner,
    SUPERVISOR_RAW_WORKER_TRACE_ENV,
    SUPERVISOR_WORKER_HEARTBEAT_ENV,
    SUPERVISOR_REPORT_NODE_TIMEOUT_ENV,
    build_supervisor_enabled_agent,
    run_supervisor_orchestration,
)


def _make_settings(tmp_path: Path) -> Mock:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    settings = Mock()
    settings.ensure_agent_dir.return_value = agent_dir
    settings.ensure_user_skills_dir.return_value = skills_dir
    settings.get_project_skills_dir.return_value = None
    settings.get_built_in_skills_dir.return_value = skills_dir
    settings.get_user_agent_md_path.return_value = agent_dir / "AGENTS.md"
    settings.get_project_agent_md_path.return_value = []
    settings.get_user_agents_dir.return_value = tmp_path / "agents"
    settings.get_project_agents_dir.return_value = None
    settings.model_name = None
    settings.model_provider = None
    settings.model_unsupported_modalities = frozenset()
    settings.model_context_limit = None
    settings.project_root = None
    settings.get_user_agent_skills_dir.return_value = skills_dir
    settings.get_project_agent_skills_dir.return_value = None
    settings.get_user_claude_skills_dir.return_value = tmp_path / "claude"
    settings.get_project_claude_skills_dir.return_value = None
    return settings


@pytest.mark.asyncio
async def test_classify_task_for_supervisor_uses_llm_when_confident() -> None:
    model = Mock()
    model.ainvoke = AsyncMock(
        return_value=AIMessage(
            content='{"task_type":"report","confidence":0.91,"reason":"Formal risk assessment request.","matched_signals":["风险评估","WHO 风格"]}'
        )
    )

    classification, details = await classify_task_with_model(
        model=model,
        task="请按 WHO 风格写一份 XFG.1.1 毒株风险评估报告。",
    )

    assert classification.primary_type == "report"
    assert details["source"] == "llm_classifier"
    assert details["confidence"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_classify_task_for_supervisor_falls_back_to_rules_on_invalid_output() -> None:
    model = Mock()
    model.ainvoke = AsyncMock(return_value=AIMessage(content="not json"))

    classification, details = await classify_task_with_model(
        model=model,
        task="基于仓库中涉及的真实测试数据和任务脚本信息，仓库地址：https://github.com/ablab/spades",
    )

    assert classification.primary_type == "github2workspace"
    assert details["source"] == "rules_fallback"
    assert details["llm_error"] == "invalid_classifier_output"
    assert details["llm_attempts"][0]["content_preview"] == "not json"


@pytest.mark.asyncio
async def test_build_supervisor_enabled_agent_returns_refusal_message_from_classifier(
    tmp_path: Path,
) -> None:
    base_agent = AsyncMock()
    fallback_agent = AsyncMock()

    class _Classifier:
        async def ainvoke(self, _messages):
            return AIMessage(
                content="",
                response_metadata={
                    "model_name": "claude-sonnet-4-6",
                    "model_provider": "anthropic",
                    "stop_reason": "refusal",
                },
            )

    agent = build_supervisor_enabled_agent(
        base_agent=base_agent,
        fallback_agent=fallback_agent,
        workspace_root=tmp_path,
        classifier_model=_Classifier(),
        enable_generic_ask_user=False,
    )

    result = await agent.ainvoke({"messages": [HumanMessage(content="test task")]})

    assert result["messages"][-1].content == "The model refused to answer this request."


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_writes_artifacts_and_stops_on_node_decision_check(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260430120000"
    workspace.mkdir(parents=True)
    attempts = {"build": 0}

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "inspect":
            return WorkerResult(status="completed", summary="inspect ok")
        if node.node_id in {"build", "retry_build"}:
            attempts["build"] += 1
            if attempts["build"] == 1:
                return WorkerResult(
                    status="failed",
                    summary="build failed",
                    failure_reason="docker_error",
                )
            return WorkerResult(status="completed", summary="build ok")
        if node.node_id == "wdl":
            return WorkerResult(status="completed", summary="wdl ok")
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await run_supervisor_orchestration(
        task="把这个 GitHub 仓库变成有工作流的可运行 workspace：https://github.com/ablab/spades",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    run_dir = result.run_dir
    assert (run_dir / "request.json").exists()
    assert (run_dir / "retrieved_cases.json").exists()
    assert (run_dir / "graph_round_1.json").exists()
    assert not (run_dir / "graph_round_2.json").exists()
    assert (run_dir / "final_decision.json").exists()
    assert (run_dir / "final_summary.md").exists()
    assert (run_dir / "evaluation.json").exists()
    assert (run_dir / "worker_outputs" / "build.json").exists()
    assert not (run_dir / "worker_outputs" / "retry_build.json").exists()

    final_payload = json.loads((run_dir / "final_decision.json").read_text())
    evaluation_payload = json.loads((run_dir / "evaluation.json").read_text())
    assert final_payload["decision"] == "stop"
    assert final_payload["reason"] == "Node decision check requested finalization."
    assert final_payload["failed_nodes"] == ["build"]
    assert evaluation_payload["task_family"] == "github2workspace"
    assert evaluation_payload["completion_status"] == "partial"
    assert evaluation_payload["false_positive"] is False
    assert result.round_count == 1


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_supports_report_tasks(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260430130000"
    workspace.mkdir(parents=True)

    async def worker_runner(node: TaskNode) -> WorkerResult:
        return WorkerResult(
            status="completed",
            summary=f"{node.node_id} ok",
            artifacts=[f"{node.node_id}.md"],
        )

    result = await run_supervisor_orchestration(
        task="写一份近期全球呼吸系统病原流行情况报告（新冠、流感、RSV），附 evidence layers。",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    run_dir = result.run_dir
    final_payload = json.loads((run_dir / "final_decision.json").read_text())
    graph_payload = json.loads((run_dir / "graph_round_1.json").read_text())

    assert final_payload["task_type"] == "report"
    assert final_payload["decision"] == "stop"
    assert graph_payload["task_type"] == "report"
    assert (run_dir / "worker_outputs" / "compose_report.json").exists()


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_supports_generic_tasks(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260430133000"
    workspace.mkdir(parents=True)

    async def worker_runner(node: TaskNode) -> WorkerResult:
        assert node.node_id in {
            "init_generic",
            "compose_generic",
            "summarize",
            "final_response",
        }
        if node.node_id == "init_generic":
            return WorkerResult(
                status="completed",
                summary="planned flexible direct-answer graph",
                spawned_subgraph={
                    "nodes": [
                        {
                            "node_id": "compose_generic",
                            "title": "Compose direct answer",
                            "objective": "Answer the user directly.",
                            "capability_bundles": ["summarize", "validate"],
                        },
                        {
                            "node_id": "summarize",
                            "title": "Summarize",
                            "objective": "Summarize the answer.",
                            "capability_bundles": ["summarize"],
                        },
                    ],
                    "edges": [{"source": "compose_generic", "target": "summarize"}],
                },
            )
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await run_supervisor_orchestration(
        task="帮我整理这个任务的执行思路并给出下一步建议。",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    run_dir = result.run_dir
    graph_1_payload = json.loads((run_dir / "graph_round_1.json").read_text())
    graph_2_payload = json.loads((run_dir / "graph_round_2.json").read_text())
    final_payload = json.loads((run_dir / "final_decision.json").read_text())
    assert graph_1_payload["task_type"] == "generic"
    assert [node["node_id"] for node in graph_1_payload["nodes"]] == [
        "init_generic",
    ]
    assert [node["node_id"] for node in graph_2_payload["nodes"]] == [
        "compose_generic",
        "summarize",
    ]
    assert graph_2_payload["metadata"]["planner_generated"] is True
    assert final_payload["generic_approach"] is None
    assert not (run_dir / "generic_approach_options.json").exists()
    assert not (run_dir / "generic_approach_selection.json").exists()


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_uses_generic_fallback_when_init_returns_no_subgraph(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260518173000"
    workspace.mkdir(parents=True)
    seen: list[str] = []

    async def worker_runner(node: TaskNode) -> WorkerResult:
        seen.append(node.node_id)
        if node.node_id == "init_generic":
            return WorkerResult(status="completed", summary="Worker completed.")
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await run_supervisor_orchestration(
        task="最近两周国内新冠和流感大概是什么态势？先给我一个口头判断，不要正式写作。",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    graph_2_payload = json.loads((result.run_dir / "graph_round_2.json").read_text())

    assert seen[:5] == [
        "init_generic",
        "worker_context",
        "worker_solution",
        "compose_generic",
        "summarize",
    ]
    assert [node["node_id"] for node in graph_2_payload["nodes"]] == [
        "worker_context",
        "worker_solution",
        "compose_generic",
        "summarize",
    ]
    assert graph_2_payload["metadata"].get("planner_generated") is not True
    assert result.final_decision.decision == "stop"


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_returns_user_facing_response(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260430134500"
    workspace.mkdir(parents=True)

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "init_generic":
            return WorkerResult(
                status="completed",
                summary="planned greeting graph",
                spawned_subgraph={
                    "nodes": [
                        {
                            "node_id": "direct_greeting_reply",
                            "title": "Generate greeting",
                            "objective": "Reply to the greeting.",
                            "capability_bundles": ["summarize"],
                        },
                        {
                            "node_id": "final_summarize",
                            "title": "Final answer",
                            "objective": "Produce the final user-facing answer.",
                            "capability_bundles": ["summarize", "validate"],
                        },
                    ],
                    "edges": [
                        {
                            "source": "direct_greeting_reply",
                            "target": "final_summarize",
                        }
                    ],
                },
            )
        if node.node_id == "direct_greeting_reply":
            return WorkerResult(
                status="completed",
                summary='已生成回复："你好！很高兴见到你。"',
            )
        if node.node_id == "final_summarize":
            return WorkerResult(status="completed", summary="你好！很高兴见到你。")
        if node.node_id == "final_response":
            return WorkerResult(status="completed", summary="你好！很高兴见到你。")
        return WorkerResult(
            status="completed",
            summary=(
                "最强已验证结果：最终回复为“你好！很高兴见到你。”\n\n"
                "worker 贡献：已完成。\n\n下一步建议：直接发送。"
            ),
        )

    result = await run_supervisor_orchestration(
        task="你好",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    assert result.user_response == "你好！很高兴见到你。"
    assert "Supervisor Summary" in result.final_summary
    assert (result.run_dir / "final_response.md").read_text(encoding="utf-8") == (
        "你好！很高兴见到你。"
    )


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_stops_on_worker_refusal(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260430134600"
    workspace.mkdir(parents=True)

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "init_generic":
            return WorkerResult(
                status="completed",
                summary="planned one-node graph",
                spawned_subgraph={
                    "nodes": [
                        {
                            "node_id": "worker_solution",
                            "title": "Solve",
                            "objective": "Solve the task.",
                            "capability_bundles": ["summarize"],
                        }
                    ],
                    "edges": [],
                },
            )
        raise ModelRefusalError(
            message="The model refused to answer this request.",
            stage=f"worker:{node.node_id}",
        )

    result = await run_supervisor_orchestration(
        task="帮我做一个会被拒绝的请求。",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    assert result.user_response == "The model refused to answer this request."
    assert result.final_decision.reason == "model_refusal:worker:worker_solution"
    assert (result.run_dir / "final_response.md").read_text(encoding="utf-8") == (
        "The model refused to answer this request."
    )


def test_sqlite_case_index_rebuild_and_retrieve(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "20260430120000" / "orchestration_runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "request.json").write_text(
        json.dumps({"task": "benchmark spades megahit covid assembly"}),
        encoding="utf-8",
    )
    (run_dir / "final_decision.json").write_text(
        json.dumps({"decision": "stop", "task_type": "benchmark"}),
        encoding="utf-8",
    )
    (run_dir / "final_summary.md").write_text(
        "spades and megahit benchmark summary",
        encoding="utf-8",
    )

    index = SQLiteCaseIndex(workspace_root / "orchestration_case_index.sqlite3")
    index.rebuild_from_workspace_root(workspace_root)
    hits = index.search("megahit benchmark", limit=3)

    assert hits
    assert hits[0].task_type == "benchmark"
    assert "megahit" in hits[0].summary


def test_latest_human_route_mode_reads_fallback_override() -> None:
    state = {
        "messages": [
            HumanMessage(content="hello"),
            HumanMessage(
                content="plain chat",
                additional_kwargs={"code2workspace_route": "fallback"},
            ),
        ]
    }

    assert _latest_human_route_mode(state) == "fallback"


@pytest.mark.asyncio
async def test_run_worker_and_capture_logs_and_reraises_interrupt(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-interrupt"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="execute_task",
        title="Execute",
        objective="execute",
        capability_bundles=["validate"],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        await _run_worker_and_capture(
            node=node,
            graph_round=2,
            run_dir=run_dir,
            worker_runner=worker_runner,
        )

    activity = (run_dir / "tool_activity.jsonl").read_text(encoding="utf-8")
    assert '"event": "node_started"' in activity
    assert '"event": "node_interrupted"' in activity


@pytest.mark.asyncio
async def test_run_worker_and_capture_times_out_report_nodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-timeout"
    run_dir.mkdir(parents=True)
    monkeypatch.setenv(SUPERVISOR_REPORT_NODE_TIMEOUT_ENV, "0.01")
    node = TaskNode(
        node_id="monitoring_lane",
        title="Monitoring lane",
        objective="collect monitoring evidence",
        capability_bundles=["web_search", "web_fetch", "validate"],
        metadata={"task_type": "report"},
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        await asyncio.sleep(10)
        return WorkerResult(status="completed", summary="too late")

    result = await _run_worker_and_capture(
        node=node,
        graph_round=1,
        run_dir=run_dir,
        worker_runner=worker_runner,
    )

    assert result.status == "partial"
    assert result.failure_reason == "worker_timeout"
    activity = (run_dir / "tool_activity.jsonl").read_text(encoding="utf-8")
    assert '"event": "node_timeout"' in activity
    payload = json.loads((run_dir / "worker_outputs" / "monitoring_lane.json").read_text())
    assert payload["result"]["failure_reason"] == "worker_timeout"


@pytest.mark.asyncio
async def test_run_worker_and_capture_emits_heartbeat_for_long_running_nodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-heartbeat"
    run_dir.mkdir(parents=True)
    monkeypatch.setenv(SUPERVISOR_WORKER_HEARTBEAT_ENV, "0.01")
    node = TaskNode(
        node_id="inspect",
        title="Inspect",
        objective="inspect repository",
        capability_bundles=["read_file", "validate"],
    )

    async def worker_runner(node: TaskNode) -> WorkerResult:  # noqa: ARG001
        await asyncio.sleep(0.035)
        return WorkerResult(status="completed", summary="done")

    result = await _run_worker_and_capture(
        node=node,
        graph_round=1,
        run_dir=run_dir,
        worker_runner=worker_runner,
    )

    assert result.status == "completed"
    activity = (run_dir / "tool_activity.jsonl").read_text(encoding="utf-8")
    assert '"event": "node_started"' in activity
    assert '"event": "node_heartbeat"' in activity
    assert '"event": "node_finished"' in activity


def test_create_cli_agent_wraps_default_agent_with_supervisor_runtime(
    tmp_path: Path,
) -> None:
    mock_wrapped_agent = Mock()
    mock_wrapped_agent.with_config.return_value = mock_wrapped_agent
    fake_model = Mock()
    fake_model.profile = {"max_input_tokens": 200000}
    resolved_report_model = Mock()
    resolved_report_model.profile = {"max_input_tokens": 1000000}
    built_agents: list[Mock] = []

    def _fake_workspace_agent(**_: object) -> Mock:
        agent = Mock()
        agent.with_config.return_value = agent
        built_agents.append(agent)
        return agent

    with (
        patch.dict("os.environ", {}, clear=True),
        patch("code2workspace_cli.agent.settings", _make_settings(tmp_path)),
        patch("code2workspace_cli.agent.create_workspace_agent", side_effect=_fake_workspace_agent),
        patch(
            "code2workspace_cli.agent._resolve_report_worker_model",
            return_value=resolved_report_model,
        ),
        patch("code2workspace._models.init_chat_model", return_value=fake_model),
        patch("code2workspace.middleware.summarization.create_summarization_tool_middleware"),
        patch(
            "code2workspace_cli.agent.build_supervisor_enabled_agent",
            return_value=mock_wrapped_agent,
        ) as mock_build,
    ):
        agent, _backend = create_cli_agent(
            model="fake-model",
            assistant_id="test",
            enable_memory=False,
            enable_skills=False,
            enable_shell=False,
        )

    assert agent is mock_wrapped_agent
    assert mock_build.call_count == 1
    assert len(built_agents) == 4
    assert mock_build.call_args.kwargs["base_agent"] is built_agents[0]
    assert mock_build.call_args.kwargs["worker_agent"] is built_agents[1]
    assert mock_build.call_args.kwargs["fallback_agent"] is built_agents[3]
    worker_subagents = mock_build.call_args.kwargs["worker_subagents"]
    assert len(worker_subagents) == 7
    assert {item.runnable for item in worker_subagents} == {built_agents[2]}
    assert any(
        item.name == "report:monitoring_lane"
        and item.node_ids == frozenset({"monitoring_lane", "retry_monitoring_lane"})
        for item in worker_subagents
    )


def test_create_cli_agent_allows_report_worker_model_env_overrides(
    tmp_path: Path,
) -> None:
    mock_wrapped_agent = Mock()
    mock_wrapped_agent.with_config.return_value = mock_wrapped_agent
    fake_model = Mock()
    fake_model.profile = {"max_input_tokens": 200000}
    created_models: list[object] = []
    built_agents: list[Mock] = []
    resolved_models = {
        "openai_paid:gpt-5.4": Mock(name="resolved-default-report-model"),
        "openai_paid:gpt-5.4-compose": Mock(name="resolved-compose-report-model"),
        "openai_paid:gpt-5.4-final": Mock(name="resolved-final-report-model"),
    }
    for model in resolved_models.values():
        model.profile = {"max_input_tokens": 1000000}

    def _fake_workspace_agent(**kwargs: object) -> Mock:
        agent = Mock()
        agent.with_config.return_value = agent
        built_agents.append(agent)
        created_models.append(kwargs["model"])
        return agent

    with (
        patch.dict(
            "os.environ",
            {
                "CODE2WORKSPACE_SUPERVISOR_REPORT_MODEL": "openai_paid:gpt-5.4",
                "CODE2WORKSPACE_SUPERVISOR_REPORT_COMPOSE_MODEL": "openai_paid:gpt-5.4-compose",
                "CODE2WORKSPACE_SUPERVISOR_REPORT_FINAL_RESPONSE_MODEL": "openai_paid:gpt-5.4-final",
            },
            clear=True,
        ),
        patch("code2workspace_cli.agent.settings", _make_settings(tmp_path)),
        patch("code2workspace_cli.agent.create_workspace_agent", side_effect=_fake_workspace_agent),
        patch(
            "code2workspace_cli.agent._resolve_report_worker_model",
            side_effect=lambda spec: resolved_models[spec],
        ) as mock_resolve_report_model,
        patch("code2workspace._models.init_chat_model", return_value=fake_model),
        patch("code2workspace.middleware.summarization.create_summarization_tool_middleware"),
        patch(
            "code2workspace_cli.agent.build_supervisor_enabled_agent",
            return_value=mock_wrapped_agent,
        ) as mock_build,
    ):
        create_cli_agent(
            model="fake-model",
            assistant_id="test",
            enable_memory=False,
            enable_skills=False,
            enable_shell=False,
        )

    assert created_models.count(resolved_models["openai_paid:gpt-5.4"]) == 1
    assert resolved_models["openai_paid:gpt-5.4-compose"] in created_models
    assert resolved_models["openai_paid:gpt-5.4-final"] in created_models
    assert [item.args[0] for item in mock_resolve_report_model.call_args_list] == [
        "openai_paid:gpt-5.4",
        "openai_paid:gpt-5.4-compose",
        "openai_paid:gpt-5.4-final",
    ]
    worker_subagents = mock_build.call_args.kwargs["worker_subagents"]
    by_name = {item.name: item for item in worker_subagents}
    assert by_name["report:compose_report"].runnable is built_agents[3]
    assert by_name["report:final_response"].runnable is built_agents[4]


def test_resolve_report_worker_model_falls_back_from_openai_paid_alias() -> None:
    primary_error = Exception("unsupported provider")
    resolved_fallback = Mock()
    resolved_fallback.profile = {"max_input_tokens": 1000000}

    with patch("code2workspace_cli.config.create_model") as mock_create_model:
        mock_create_model.side_effect = [
            __import__("code2workspace_cli.model_config", fromlist=["ModelConfigError"]).ModelConfigError(primary_error),
            Mock(model=resolved_fallback),
        ]

        model = __import__("code2workspace_cli.agent", fromlist=["_resolve_report_worker_model"])._resolve_report_worker_model(
            "openai_paid:gpt-5.4"
        )

    assert model is resolved_fallback
    assert [call.args[0] for call in mock_create_model.call_args_list] == [
        "openai_paid:gpt-5.4",
        "openai:gpt-5.4",
    ]


def test_build_worker_prompt_uses_capability_registry_and_guidance() -> None:
    node = TaskNode(
        node_id="inspect",
        title="Inspect repository",
        objective="Inspect repository assets",
        capability_bundles=["repo_fetch", "validate"],
        metadata={
            "guidance_ids": ["github2workspace_pipeline"],
            "task": "把这个 GitHub 仓库变成有工作流的可运行 workspace：https://github.com/ablab/spades",
            "task_paths": ["/tmp/supervisor-workspace"],
            "run_dir": "/tmp/supervisor-workspace/orchestration_runs/run-1",
            "prior_worker_outputs": ["/tmp/supervisor-workspace/orchestration_runs/run-1/worker_outputs/register.json"],
            "prior_node_traces": ["/tmp/supervisor-workspace/orchestration_runs/run-1/node_traces/register.json"],
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "Preferred tool surface:" in prompt
    assert "execute" in prompt
    assert "read_file" in prompt
    assert "Capability details:" in prompt
    assert "repo_fetch" in prompt
    assert "validate" in prompt
    assert "materialize the repository into the current workspace" in prompt
    assert "inspect that local copy directly instead of re-cloning it" in prompt
    assert "bundled datasets" in prompt
    assert "Earlier nodes may spend time discovering the safest real validation path" in prompt
    assert "Original task:" in prompt
    assert "Task paths:" in prompt
    assert "Run directory:" in prompt
    assert "Prior worker outputs:" in prompt
    assert "Node metadata summary:" in prompt


def test_build_worker_prompt_compacts_large_prior_worker_payloads() -> None:
    node = TaskNode(
        node_id="compose_generic",
        title="Compose generic answer",
        objective="Compose a normal long-form answer",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "下一波新冠/流感阳性率的高峰会在什么时间？",
            "task_type": "generic",
            "graph_round": 2,
            "prior_worker_outputs": [f"/tmp/run/worker_outputs/{i}.json" for i in range(12)],
            "prior_node_traces": [f"/tmp/run/node_traces/{i}.json" for i in range(12)],
            "run_dir_artifacts": [f"/tmp/run/artifacts/{i}.json" for i in range(12)],
            "prior_worker_output_payloads": {
                "worker_context.json": {
                    "node_id": "worker_context",
                    "status": "completed",
                    "summary": "context ok",
                    "artifacts_count": 2,
                    "evidence_count": 5,
                }
            },
            "retrieved_cases": [
                {"task_type": "generic", "summary": "a" * 4000},
                {"task_type": "report", "summary": "b" * 4000},
            ],
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "... 4 more paths omitted" in prompt
    assert "retrieved_case_count" in prompt
    assert "retrieved_case_types" in prompt
    assert '"status": "completed"' in prompt
    assert '"summary": "context ok"' in prompt
    assert "where the evidence came from" in prompt
    assert "direct evidence, inferred evidence, or unresolved gaps" in prompt
    assert "aaaa" not in prompt
    assert "bbbb" not in prompt


def test_build_worker_prompt_github2workspace_build_requires_early_observable_action() -> None:
    node = TaskNode(
        node_id="build",
        title="Build Docker image",
        objective="Build or repair the Docker image and run a minimal container validation attempt.",
        capability_bundles=["docker_build_run", "validate"],
        metadata={
            "task": "Convert this GitHub repository into a runnable workspace and generate Docker and WDL validation paths: https://github.com/egaffo/circompara2",
            "task_type": "github2workspace",
            "guidance_ids": ["github2workspace_pipeline"],
            "graph_round": 1,
            "run_dir": "/tmp/supervisor-workspace/orchestration_runs/run-1",
            "prior_worker_outputs": [
                "/tmp/supervisor-workspace/orchestration_runs/run-1/worker_outputs/inspect.json"
            ],
            "prior_node_traces": [
                "/tmp/supervisor-workspace/orchestration_runs/run-1/node_traces/inspect.json"
            ],
            "prior_worker_output_payloads": {
                "inspect.json": {
                    "node_id": "inspect",
                    "status": "completed",
                    "summary": "inspect done",
                    "next_action_hint": "Use the documented image first.",
                }
            },
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "consuming the latest inspect artifact" in prompt
    assert "perform at least one concrete observable step" in prompt
    assert "checking for an existing Dockerfile" in prompt
    assert "verifying a documented image" in prompt
    assert "official image" in prompt
    assert "thin wrapper image" in prompt
    assert "full environment rebuild" in prompt
    assert "private-only references" in prompt
    assert "author-machine absolute paths" in prompt


def test_build_worker_prompt_final_response_preserves_evidence_sources() -> None:
    node = TaskNode(
        node_id="final_response",
        title="Write final user response",
        objective="Turn the supervisor run result into the final answer shown to the user.",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "写一份风险研判",
            "task_type": "report",
            "final_summary": "summary",
            "final_decision": "stop",
            "final_decision_reason": "done",
            "failed_nodes": [],
            "fallback_candidate": "candidate",
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "brief evidence-source explanation" in prompt
    assert "source categories" in prompt
    assert "direct-vs-inferred evidence distinctions" in prompt
    assert "判断轨迹（可审计摘要）" in prompt
    assert "auditable reasoning path" in prompt
    assert "not private chain-of-thought" in prompt
    assert "false positives" in prompt


def test_build_worker_prompt_report_final_response_preserves_report_template() -> None:
    node = TaskNode(
        node_id="final_response",
        title="Write final user response",
        objective="Turn the supervisor run result into the final answer shown to the user.",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "请写一份中文风险评估报告",
            "task_type": "report",
            "final_summary": "# 风险评估报告\n\n## 执行摘要\n...",
            "final_decision": "stop",
            "final_decision_reason": "done",
            "failed_nodes": [],
            "fallback_candidate": "# 风险评估报告",
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "structured Markdown deliverable" in prompt
    assert "title, executive summary, scope/time window" in prompt
    assert "same language as the user's report request" in prompt
    assert "evidence appendix" in prompt
    assert "preserve the numbering and include the source list" in prompt
    assert "traceable to a finding" in prompt


def test_build_worker_prompt_compose_report_includes_template_guidance() -> None:
    node = TaskNode(
        node_id="compose_report",
        title="Compose report",
        objective="Compose a full-length report from the completed lanes.",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "请写一份中文风险评估报告",
            "task_type": "report",
            "guidance_ids": ["report_synthesis"],
            "run_dir": "/tmp/supervisor-run",
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "Use this default report structure" in prompt
    assert "Executive Summary" in prompt
    assert "Section quality requirements" in prompt
    assert "Citation and source rules" in prompt
    assert "If the report is a risk assessment" in prompt


def test_build_worker_prompt_monitoring_lane_includes_source_priority_and_depth_policy() -> None:
    node = TaskNode(
        node_id="monitoring_lane",
        title="Monitoring lane",
        objective="Collect monitoring evidence.",
        capability_bundles=["web_search", "web_fetch", "api_call", "validate"],
        metadata={
            "task": "请写一份近期呼吸道疾病监测报告",
            "task_type": "report",
            "guidance_ids": ["report_synthesis"],
            "run_dir": "/tmp/supervisor-run",
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "Establish scope before depth" in prompt
    assert "user-specified sources" in prompt
    assert "whitelisted official or primary sources" in prompt
    assert "Default to D2 evidence depth" in prompt
    assert "Escalate to D3" in prompt
    assert "Escalate to D4" in prompt
    assert "full-web search only for source discovery" in prompt


def test_build_worker_prompt_generic_context_defaults_to_d2_for_evidence_tasks() -> None:
    node = TaskNode(
        node_id="worker_context",
        title="Collect generic context",
        objective="Collect source-backed context for a generic judgment task.",
        capability_bundles=["web_search", "web_fetch", "db_access", "validate"],
        metadata={
            "task": "下一波新冠/流感阳性率的高峰会在什么时间？给我一个口头判断但要有证据边界。",
            "task_type": "generic",
            "guidance_ids": [],
            "run_dir": "/tmp/supervisor-run",
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "use the same D2 default evidence depth as report monitoring lanes" in prompt
    assert "Scope before depth" in prompt
    assert "curated project skills/local stores/structured APIs" in prompt
    assert "Escalate to D3" in prompt
    assert "D0-D1" in prompt


def test_build_worker_prompt_init_generic_plans_operator_store_computation() -> None:
    node = TaskNode(
        node_id="init_generic",
        title="Plan generic graph",
        objective="Analyze the generic user request and create a flexible execution graph.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task": "下一波新冠/流感阳性率高峰在什么时候？如果需要计算，就用本地算子预测，先给我一个口头判断。",
            "task_type": "generic",
            "guidance_ids": [],
            "run_dir": "/tmp/supervisor-run",
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "searches operator_store for candidate operators" in prompt
    assert "selects a compatible local dataset/input bundle" in prompt
    assert "runs the concrete WDL/Docker/entrypoint path" in prompt
    assert "metric_compute" in prompt
    assert "operator_filter" in prompt
    assert "spawned_subgraph" in prompt


def test_build_worker_prompt_local_data_report_includes_benchmark_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    store = BenchmarkResultStore(tmp_path / "benchmark_comparison_history_store")
    result_file = tmp_path / "assembly.fasta"
    result_file.write_text(">contig\nACGT\n", encoding="utf-8")
    record = {
        "repo": "Flye",
        "operator_id": "github2workspace:Flye",
        "dataset_key": "long-read-pacbio",
        "workflow_signature": "wf-1",
        "input_signature": "in-1",
        "success": True,
        "returncode": 0,
        "run_id": "run-flye",
        "run_dir": str(tmp_path / "runs" / "run-flye"),
        "case_dir": str(tmp_path / "runs" / "run-flye" / "cases" / "Flye"),
        "workflow_path": str(tmp_path / "flye.wdl"),
        "inputs_json_path": str(tmp_path / "inputs.json"),
        "status_path": str(tmp_path / "status.json"),
        "wdl_status_path": str(tmp_path / "wdl-status.json"),
        "result_manifest_path": str(tmp_path / "result_manifest.json"),
        "analysis_path": str(tmp_path / "analysis.json"),
        "result_files": [str(result_file)],
        "status_payload": {"success": True},
        "wdl_status_payload": {"success": True},
        "result_manifest": {"success": True},
        "analysis_payload": {"metrics": {"n50": 1234, "contig_count": 2}},
        "canonical_text": "long read pacbio assembly benchmark result",
    }
    with patch(
        "code2workspace_cli.benchmark_result_store._embed_documents",
        return_value=([], ""),
    ):
        store.write_record(record)
    operator_store = OperatorStore(tmp_path / "operator_store")
    workflow_path = tmp_path / "flye.wdl"
    inputs_json_path = tmp_path / "flye.inputs.json"
    reads_path = tmp_path / "pacbio.fastq.gz"
    workflow_path.write_text("workflow FlyeWorkflow {}", encoding="utf-8")
    inputs_json_path.write_text("{}", encoding="utf-8")
    reads_path.write_text("reads", encoding="utf-8")
    operator_store.write_manifest(
        {
            "product_id": "benchmark:Flye:test",
            "operator_id": "benchmark:Flye",
            "name": "Flye",
            "family": "benchmark",
            "version": "test",
            "status": "registered_ready",
            "summary": "Long read PacBio assembly operator.",
            "created_at": "2026-05-18T00:00:00Z",
            "runtime": {
                "backend": "wdl",
                "image_ref": "benchmark/flye:test",
                "workflow_path": str(workflow_path),
                "inputs_json_path": str(inputs_json_path),
            },
            "inputs": [
                {
                    "name": "reads",
                    "media_type": "fastq",
                    "path": str(reads_path),
                    "schema_path": "",
                    "required": True,
                }
            ],
            "outputs": [
                {
                    "name": "assembly",
                    "media_type": "fasta",
                    "path": "assembly.fasta",
                    "schema_path": "",
                    "required": False,
                }
            ],
            "metrics": [{"name": "n50", "type": "numeric", "description": "Assembly N50."}],
            "validation": {
                "validation_id": "benchmark:Flye:test",
                "status": "registered_ready",
                "dataset_id": "long-read-pacbio",
                "run_dir": str(tmp_path / "run"),
                "summary": "ready",
                "created_at": "2026-05-18T00:00:00Z",
            },
            "tags": ["benchmark", "execution-ready", "long-read"],
        }
    )
    node = TaskNode(
        node_id="local_data_lane",
        title="Local data lane",
        objective="Collect local structured evidence.",
        capability_bundles=["db_access", "api_call", "validate"],
        metadata={
            "task": "请写一份 long read PacBio assembly benchmark 报告",
            "task_type": "report",
            "guidance_ids": ["report_synthesis"],
        },
    )

    prompt = _build_worker_prompt(node=node, workspace_root=tmp_path)

    assert "Report local data source context:" in prompt
    assert "existing_data" in prompt
    assert "computed_data" in prompt
    assert "operator_store records as the local operator library" in prompt
    assert "Candidate local operators for computed_data:" in prompt
    assert "operator_id=benchmark:Flye" in prompt
    assert "inputs_json=" in prompt
    assert "Candidate local datasets/input bundles:" in prompt
    assert "repo=Flye" in prompt
    assert "dataset_key=long-read-pacbio" in prompt
    assert '"n50": 1234' in prompt
    assert "record_path=" in prompt


def test_build_worker_prompt_generic_context_includes_local_computation_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    workflow_path = tmp_path / "forecast.wdl"
    inputs_json_path = tmp_path / "forecast.inputs.json"
    dataset_path = tmp_path / "surveillance.csv"
    workflow_path.write_text("workflow ForecastWorkflow {}", encoding="utf-8")
    inputs_json_path.write_text("{}", encoding="utf-8")
    dataset_path.write_text("week,positivity\n2026-W18,0.12\n", encoding="utf-8")
    store = OperatorStore(tmp_path / "operator_store")
    store.write_manifest(
        {
            "product_id": "analysis:respiratory-forecast:test",
            "operator_id": "analysis:respiratory-forecast",
            "name": "respiratory-forecast",
            "family": "analysis",
            "version": "test",
            "status": "completed",
            "summary": "Forecast respiratory positivity peaks from local surveillance time series.",
            "created_at": "2026-05-18T00:00:00Z",
            "runtime": {
                "backend": "wdl",
                "image_ref": "local/forecast:test",
                "workflow_path": str(workflow_path),
                "inputs_json_path": str(inputs_json_path),
            },
            "inputs": [
                {
                    "name": "surveillance_csv",
                    "media_type": "csv",
                    "path": str(dataset_path),
                    "schema_path": "",
                    "required": True,
                }
            ],
            "outputs": [
                {
                    "name": "forecast_json",
                    "media_type": "json",
                    "path": "forecast.json",
                    "schema_path": "",
                    "required": False,
                }
            ],
            "metrics": [],
            "validation": {
                "validation_id": "analysis:respiratory-forecast:test",
                "status": "completed",
                "dataset_id": "respiratory-surveillance",
                "run_dir": str(tmp_path / "run"),
                "summary": "completed",
                "created_at": "2026-05-18T00:00:00Z",
            },
            "tags": ["forecast", "respiratory", "local-data"],
        }
    )
    node = TaskNode(
        node_id="worker_context",
        title="Collect context",
        objective="Collect local evidence and compute a forecast if needed.",
        capability_bundles=["db_access", "operator_filter", "metric_compute", "validate"],
        metadata={
            "task": "下一波新冠/流感阳性率的高峰会在什么时间？需要时用本地算子预测。",
            "task_type": "generic",
        },
    )

    prompt = _build_worker_prompt(node=node, workspace_root=tmp_path)

    assert "Local computation context:" in prompt
    assert "existing_data" in prompt
    assert "computed_data" in prompt
    assert "operator_id=analysis:respiratory-forecast" in prompt
    assert "surveillance.csv" in prompt
    assert "End local computation context." in prompt


@pytest.mark.asyncio
async def test_report_local_data_lane_can_run_operator_from_prompt_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    workspace_root = tmp_path / "workspace" / "20260518120000"
    workspace_root.mkdir(parents=True)
    data_dir = workspace_root / "local_data"
    data_dir.mkdir()
    dataset_path = data_dir / "respiratory_surveillance.csv"
    dataset_path.write_text(
        "week,positivity\n2026-W18,0.12\n2026-W19,0.18\n2026-W20,0.15\n",
        encoding="utf-8",
    )
    entrypoint_path = data_dir / "forecast_peak.py"
    entrypoint_path.write_text(
        "\n".join(
            [
                "import csv, json, sys",
                "dataset_path, output_path = sys.argv[1], sys.argv[2]",
                "with open(dataset_path, encoding='utf-8') as handle:",
                "    rows = list(csv.DictReader(handle))",
                "best = max(rows, key=lambda row: float(row['positivity']))",
                "payload = {'peak_week': best['week'], 'peak_positivity': float(best['positivity']), 'row_count': len(rows)}",
                "with open(output_path, 'w', encoding='utf-8') as handle:",
                "    json.dump(payload, handle, ensure_ascii=False, sort_keys=True)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    inputs_json_path = data_dir / "forecast.inputs.json"
    inputs_json_path.write_text(
        json.dumps(
            {
                "dataset_path": str(dataset_path),
                "output_path": "forecast_result.json",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = OperatorStore(workspace_root / "operator_store")
    store.write_manifest(
        {
            "product_id": "analysis:respiratory-peak-forecast:test",
            "operator_id": "analysis:respiratory-peak-forecast",
            "name": "respiratory-peak-forecast",
            "family": "analysis",
            "version": "test",
            "status": "completed",
            "summary": "Compute the peak respiratory positivity week from local surveillance CSV data.",
            "created_at": "2026-05-18T00:00:00Z",
            "runtime": {
                "backend": "python",
                "entrypoint": str(entrypoint_path),
                "inputs_json_path": str(inputs_json_path),
            },
            "inputs": [
                {
                    "name": "surveillance_csv",
                    "media_type": "csv",
                    "path": str(dataset_path),
                    "schema_path": "",
                    "required": True,
                }
            ],
            "outputs": [
                {
                    "name": "forecast_json",
                    "media_type": "json",
                    "path": "forecast_result.json",
                    "schema_path": "",
                    "required": False,
                }
            ],
            "metrics": [
                {
                    "name": "peak_positivity",
                    "type": "numeric",
                    "description": "Maximum positivity observed in the local time series.",
                }
            ],
            "validation": {
                "validation_id": "analysis:respiratory-peak-forecast:test",
                "status": "completed",
                "dataset_id": "respiratory-surveillance-local",
                "run_dir": str(workspace_root / "operator-validation"),
                "summary": "completed",
                "created_at": "2026-05-18T00:00:00Z",
            },
            "tags": ["forecast", "respiratory", "local-data", "operator-store"],
        }
    )

    class LocalDataLaneAgent:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def ainvoke(self, payload, **_kwargs):
            prompt = payload["messages"][0].content
            self.prompts.append(prompt)
            assert "Node ID: local_data_lane" in prompt
            assert "Report local data source context:" in prompt
            assert "operator_id=analysis:respiratory-peak-forecast" in prompt
            assert f"entrypoint={entrypoint_path}" in prompt
            run_dir_line = next(
                line for line in prompt.splitlines() if line.startswith("Run directory: ")
            )
            run_dir = Path(run_dir_line.removeprefix("Run directory: ").strip())
            output_path = run_dir / "local_data_lane" / "forecast_result.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(
                [sys.executable, str(entrypoint_path), str(dataset_path), str(output_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr
            result_payload = json.loads(output_path.read_text(encoding="utf-8"))
            lane_brief_path = output_path.with_suffix(".md")
            lane_brief_path.write_text(
                "\n".join(
                    [
                        "# Local Data Lane",
                        "",
                        "- computed_data: local operator `analysis:respiratory-peak-forecast`",
                        f"- peak_week: `{result_payload['peak_week']}`",
                        f"- peak_positivity: `{result_payload['peak_positivity']}`",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            return {
                "messages": [
                    AIMessage(
                        content=json.dumps(
                            {
                                "status": "completed",
                                "summary": (
                                    "local_data_lane ran operator "
                                    "analysis:respiratory-peak-forecast and computed "
                                    f"peak_week={result_payload['peak_week']}."
                                ),
                                "artifacts": [str(output_path), str(lane_brief_path)],
                                "evidence": [
                                    str(dataset_path),
                                    str(entrypoint_path),
                                    str(output_path),
                                ],
                                "next_action_hint": "Use computed_data in compose_report.",
                                "failure_reason": None,
                                "spawned_subgraph": {},
                            },
                            ensure_ascii=False,
                        )
                    )
                ]
            }

    local_data_agent = LocalDataLaneAgent()

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "init_report":
            return WorkerResult(
                status="completed",
                summary="report contract initialized for local computation test",
                artifacts=[str(workspace_root / "report_contract.md")],
            )
        if node.node_id == "local_data_lane":
            return await _invoke_worker_agent(
                agent=local_data_agent,
                node=node,
                workspace_root=workspace_root,
            )
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await run_supervisor_orchestration(
        task="请写一份本地呼吸道阳性率高峰预测报告，需要在 local data lane 中用本地算子计算高峰周。",
        workspace_root=workspace_root,
        worker_runner=worker_runner,
    )

    assert local_data_agent.prompts
    local_data_output = json.loads(
        (result.run_dir / "worker_outputs" / "local_data_lane.json").read_text(encoding="utf-8")
    )
    assert local_data_output["result"]["status"] == "completed"
    assert "peak_week=2026-W19" in local_data_output["result"]["summary"]
    artifact_path = Path(local_data_output["result"]["artifacts"][0])
    assert json.loads(artifact_path.read_text(encoding="utf-8")) == {
        "peak_positivity": 0.18,
        "peak_week": "2026-W19",
        "row_count": 3,
    }


def test_build_worker_prompt_benchmark_final_response_mentions_dataset_requirement(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-benchmark-final"
    run_dir.mkdir(parents=True)
    (run_dir / "dataset_resolution.json").write_text(
        json.dumps(
            {
                "repo_to_dataset": {
                    "esm": "",
                    "AutoDock-Vina": "",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metric_plan.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "repo": "esm",
                        "dataset_key": "",
                        "selected_input_files": {
                            "few_proteins.fasta": "/tmp/few_proteins.fasta",
                        },
                    },
                    {
                        "repo": "AutoDock-Vina",
                        "dataset_key": "",
                        "selected_input_files": {
                            "1iep_receptor.pdbqt": "/tmp/1iep_receptor.pdbqt",
                            "1iep_ligand.pdbqt": "/tmp/1iep_ligand.pdbqt",
                        },
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "register_report.json").write_text(
        json.dumps(
            {
                "selection_dataset_key": "",
                "shared_datasets": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    node = TaskNode(
        node_id="final_response",
        title="Write final benchmark response",
        objective="Turn benchmark results into the final user-facing answer.",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "汇总免疫逃逸 benchmark 结果。",
            "task_type": "benchmark",
            "run_dir": str(run_dir),
            "final_summary": "summary",
            "final_decision": "stop",
            "final_decision_reason": "done",
            "failed_nodes": [],
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=tmp_path,
    )

    assert "explicitly state which dataset or input bundle was actually used" in prompt
    assert "Benchmark dataset context:" in prompt
    assert "esm: dataset `unknown`, selected_inputs `few_proteins.fasta`" in prompt
    assert "AutoDock-Vina: dataset `unknown`, selected_inputs `1iep_receptor.pdbqt, 1iep_ligand.pdbqt`" in prompt


def test_benchmark_result_store_search_records_supports_semantic_query(
    tmp_path: Path,
) -> None:
    store = BenchmarkResultStore(tmp_path / "benchmark_comparison_history_store")
    result_file = tmp_path / "result.out"
    result_file.write_text("ok\n", encoding="utf-8")
    record = {
        "repo": "Flye",
        "operator_id": "github2workspace:Flye",
        "dataset_key": "long-read-pacbio",
        "workflow_signature": "wf-1",
        "input_signature": "in-1",
        "success": True,
        "returncode": 0,
        "run_id": "run-1",
        "run_dir": str(tmp_path / "run-1"),
        "case_dir": str(tmp_path / "run-1" / "cases" / "Flye"),
        "workflow_path": str(tmp_path / "flye.wdl"),
        "inputs_json_path": str(tmp_path / "inputs.json"),
        "status_path": str(tmp_path / "status.json"),
        "wdl_status_path": str(tmp_path / "wdl-status.json"),
        "result_manifest_path": str(tmp_path / "result_manifest.json"),
        "analysis_path": str(tmp_path / "analysis.json"),
        "result_files": [str(result_file)],
        "status_payload": {"success": True},
        "wdl_status_payload": {"success": True},
        "result_manifest": {"success": True},
        "analysis_payload": {"metrics": {"n50": 1234}},
        "canonical_text": "assembler genome reconstruction",
    }
    with patch(
        "code2workspace_cli.benchmark_result_store._embed_documents",
        return_value=([[1.0, 0.0]], "test-embedding-model"),
    ), patch(
        "code2workspace_cli.benchmark_result_store._embed_query",
        return_value=([1.0, 0.0], "test-embedding-model"),
    ):
        store.write_record(record)
        rows = store.search_records(
            BenchmarkResultSearchFilter(
                query="pacbio long read assembly",
                repo="Flye",
                limit=5,
            )
        )

    assert len(rows) == 1
    assert rows[0]["repo"] == "Flye"
    assert rows[0]["workflow_signature"] == "wf-1"


def test_deterministic_benchmark_case_writes_benchmark_result_history_record(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-flye-history-write"
    case_dir = run_dir / "cases" / "Flye"
    staged_wdl_dir = case_dir / "wdl"
    staged_wdl_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "run").mkdir(parents=True, exist_ok=True)
    reads = tmp_path / "pacbio.fastq"
    reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    staged_wdl = staged_wdl_dir / "flye.wdl"
    staged_inputs = staged_wdl_dir / "inputs.json"
    staged_wdl.write_text("workflow FlyeWorkflow {}", encoding="utf-8")
    staged_inputs.write_text(
        json.dumps({"FlyeWorkflow.reads_fastq": str(reads)}),
        encoding="utf-8",
    )
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo_name": "Flye",
                "operator_id": "github2workspace:Flye",
                "dataset_key": "long-read-pacbio",
                "family": "long-read-assembly",
                "metric_keys": ["contig_count", "n50"],
                "expected_outputs": [],
                "phase_status": {"register": "completed"},
                "repo_native_entry": "",
                "repo_native_command_candidates": [],
                "wdl_path": str(staged_wdl),
                "inputs_path": str(staged_inputs),
                "wdl_workflow_name": "FlyeWorkflow",
                "selected_input_files": {"reads_fastq": str(reads)},
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "execution_ready.json").write_text(
        json.dumps(
            {
                "ready": True,
                "runtime_image": "benchmark/flye",
                "wdl_path": str(staged_wdl),
                "inputs_json_path": str(staged_inputs),
            }
        ),
        encoding="utf-8",
    )
    node = TaskNode(
        node_id="Flye",
        title="Run Flye",
        objective="Execute the staged benchmark workload for Flye and record outputs.",
        capability_bundles=["wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "运行 long-read pacbio benchmark 的 Flye workflow。",
            "run_dir": str(run_dir),
        },
    )

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "run-wdl:Flye":
            output_file = case_dir / "wdl" / "assembly.fasta"
            output_file.write_text(">contig\nACGT\n", encoding="utf-8")
            (case_dir / "wdl" / "outputs.json").write_text(
                json.dumps({"outputs": {"FlyeWorkflow.assembly": str(output_file)}}),
                encoding="utf-8",
            )
            (case_dir / "wdl" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "started_at": "2026-05-17T00:00:00Z",
                        "finished_at": "2026-05-17T00:00:02Z",
                        "elapsed_seconds": 2.0,
                        "log_path": str(case_dir / "wdl" / "miniwdl_run.log"),
                        "outputs_path": str(case_dir / "wdl" / "outputs.json"),
                        "output_artifacts": [str(output_file)],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "Flye"}}
        if phase == "analyze-case:Flye":
            (case_dir / "analysis.json").write_text(
                json.dumps(
                    {
                        "family": "long-read-assembly",
                        "artifact_paths": [str(case_dir / "wdl" / "run_outputs" / "assembly.fasta")],
                        "artifact_checksums": {},
                        "metrics": {"contig_count": 1, "n50": 4},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": "Flye"}}
        raise AssertionError(f"unexpected phase: {phase}")

    with (
        patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper),
        patch("code2workspace_cli.supervisor_runtime._materialize_benchmark_operator_products", return_value=[]),
    ):
        result = supervisor_runtime._run_deterministic_benchmark_case(
            node=node,
            workspace_root=workspace_root,
            repo="Flye",
        )

    assert result.status == "completed"
    record_path = (
        workspace_root
        / "benchmark_comparison_history_store"
        / "records"
        / "Flye"
        / "run-flye-history-write"
        / "benchmark_result_record.json"
    )
    assert record_path.exists()
    record_payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_payload["repo"] == "Flye"
    assert record_payload["dataset_key"] == "long-read-pacbio"
    assert record_payload["success"] is True
    assert record_payload["workflow_signature"]
    assert record_payload["input_signature"]
    assert record_payload["result_files"] == [
        str(case_dir / "wdl" / "run_outputs" / "assembly.fasta")
    ]


def test_deterministic_benchmark_case_reuses_historical_record_before_execution(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-flye-reuse"
    case_dir = run_dir / "cases" / "Flye"
    staged_wdl_dir = case_dir / "wdl"
    staged_wdl_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "run").mkdir(parents=True, exist_ok=True)
    reads = tmp_path / "pacbio.fastq"
    reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    staged_wdl = staged_wdl_dir / "flye.wdl"
    staged_inputs = staged_wdl_dir / "inputs.json"
    staged_wdl.write_text("workflow FlyeWorkflow {}", encoding="utf-8")
    staged_inputs.write_text(
        json.dumps({"FlyeWorkflow.reads_fastq": str(reads)}),
        encoding="utf-8",
    )
    manifest_payload = {
        "repo_name": "Flye",
        "operator_id": "github2workspace:Flye",
        "dataset_key": "long-read-pacbio",
        "family": "long-read-assembly",
        "metric_keys": ["contig_count", "n50"],
        "expected_outputs": [],
        "phase_status": {"register": "completed"},
        "repo_native_entry": "",
        "repo_native_command_candidates": [],
        "wdl_path": str(staged_wdl),
        "inputs_path": str(staged_inputs),
        "wdl_workflow_name": "FlyeWorkflow",
        "selected_input_files": {"reads_fastq": str(reads)},
    }
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest_payload),
        encoding="utf-8",
    )
    (case_dir / "execution_ready.json").write_text(
        json.dumps(
            {
                "ready": True,
                "runtime_image": "benchmark/flye",
                "wdl_path": str(staged_wdl),
                "inputs_json_path": str(staged_inputs),
            }
        ),
        encoding="utf-8",
    )
    history_store = BenchmarkResultStore(workspace_root / "benchmark_comparison_history_store")
    historical_run_dir = tmp_path / "historical-run"
    historical_case_dir = historical_run_dir / "cases" / "Flye"
    historical_case_dir.mkdir(parents=True, exist_ok=True)
    historical_result = historical_case_dir / "assembly.fasta"
    historical_result.write_text(">contig\nACGT\n", encoding="utf-8")
    history_store.write_record(
        {
            "repo": "Flye",
            "operator_id": "github2workspace:Flye",
            "dataset_key": "long-read-pacbio",
            "workflow_signature": supervisor_runtime._benchmark_workflow_signature_from_manifest(manifest_payload),
            "input_signature": supervisor_runtime._benchmark_input_signature_from_manifest(manifest_payload),
            "success": True,
            "returncode": 0,
            "run_id": "historical-run-1",
            "run_dir": str(historical_run_dir),
            "case_dir": str(historical_case_dir),
            "workflow_path": str(staged_wdl),
            "inputs_json_path": str(staged_inputs),
            "status_path": str(historical_case_dir / "run" / "status.json"),
            "wdl_status_path": str(historical_case_dir / "wdl" / "status.json"),
            "result_manifest_path": str(historical_case_dir / "run" / "result_manifest.json"),
            "analysis_path": str(historical_case_dir / "analysis.json"),
            "result_files": [str(historical_result)],
            "status_payload": {
                "success": True,
                "returncode": 0,
                "command": ["run-wdl", "Flye"],
                "output_dir": str(historical_result.parent),
                "output_artifacts": [str(historical_result)],
            },
            "wdl_status_payload": {"success": True, "returncode": 0},
            "result_manifest": {"repo": "Flye", "success": True},
            "analysis_payload": {"metrics": {"contig_count": 1, "n50": 4}},
            "analysis_markdown": "# historical analysis\n",
            "canonical_text": "Flye long read pacbio assembly workflow reads_fastq",
        }
    )
    node = TaskNode(
        node_id="Flye",
        title="Run Flye",
        objective="Execute the staged benchmark workload for Flye and record outputs.",
        capability_bundles=["wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "运行 long-read pacbio benchmark 的 Flye workflow。",
            "run_dir": str(run_dir),
        },
    )

    with (
        patch(
            "code2workspace_cli.supervisor_runtime._run_helper_json_command",
            side_effect=AssertionError("historical reuse should bypass helper execution"),
        ),
        patch("code2workspace_cli.supervisor_runtime._materialize_benchmark_operator_products", return_value=[]),
    ):
        result = supervisor_runtime._run_deterministic_benchmark_case(
            node=node,
            workspace_root=workspace_root,
            repo="Flye",
        )

    assert result.status == "completed"
    assert "Reused previously computed benchmark result" in result.summary
    reused_status = json.loads((case_dir / "run" / "status.json").read_text(encoding="utf-8"))
    assert reused_status["execution_mode"] == "history_reuse"
    assert reused_status["reused_from_run_dir"] == str(historical_run_dir)
    reused_marker = json.loads(
        (case_dir / "run" / "reused_result_record.json").read_text(encoding="utf-8")
    )
    assert reused_marker["run_dir"] == str(historical_run_dir)
    assert json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))["metrics"]["n50"] == 4
    assert json.loads((case_dir / "wdl" / "status.json").read_text(encoding="utf-8"))["success"] is True


def test_build_worker_prompt_includes_wdl_node_guidance() -> None:
    node = TaskNode(
        node_id="wdl",
        title="Run WDL workflow",
        objective="Generate or repair WDL inputs and run miniwdl workflow validation.",
        capability_bundles=["wdl_run", "validate"],
        metadata={
            "guidance_ids": ["github2workspace_pipeline"],
            "task": (
                "基于仓库中涉及的真实测试数据和任务脚本信息，完成仓库镜像的构建与基础验证；"
                "编写并保存 spades_Dockerfile，构建镜像 spades，并在容器内成功运行至少一个基于真实数据的测试案例，将结果存入 results/docker_test。"
                "随后编写 spades.wdl，runtime 指定为 spades，实际运行 scripts/run-miniwdl.sh 直到出现 Succeeded，"
                "并把结果分别存入 results/wdl_result 与 results/wdl_file。仓库地址：https://github.com/ablab/spades"
            ),
            "run_dir": "/tmp/supervisor-workspace/orchestration_runs/run-2",
            "prior_worker_outputs": [
                "/tmp/supervisor-workspace/orchestration_runs/run-2/worker_outputs/inspect.json",
                "/tmp/supervisor-workspace/orchestration_runs/run-2/worker_outputs/build.json",
            ],
            "run_dir_artifacts": [
                "/tmp/supervisor-workspace/spades_Dockerfile",
                "/tmp/supervisor-workspace/results/docker_test/container_test.log",
            ],
        },
    )

    prompt = _build_worker_prompt(
        node=node,
        workspace_root=Path("/tmp/supervisor-workspace"),
    )

    assert "spades.wdl" in prompt
    assert "results/wdl_result" in prompt
    assert "Succeeded" in prompt
    assert "principal operator behavior as the primary WDL target" in prompt
    assert "smoke success alone does not mean the WDL task is complete" in prompt
    assert "Do not stop at `miniwdl check`" in prompt
    assert "workflow.log and outputs.json" in prompt
    assert "prefer a WDL runtime based on a repository-documented official image" in prompt
    assert "thin wrapper image" in prompt
    assert "private references" in prompt
    assert "never run `spades.py --test -o ...`" in prompt
    assert "copy the default `spades_test` directory" in prompt
    assert "Do not fabricate or synthesize reads" in prompt


def test_github2workspace_product_status_rejects_synthetic_inputs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "results" / "wdl_result").mkdir(parents=True)
    (workspace / "results" / "wdl_result" / "outputs.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (workspace / "results" / "wdl_file").mkdir(parents=True)
    (workspace / "results" / "wdl_file" / "toy_reads.fastq").write_text(
        "@r1\nACGT\n+\n!!!!\n",
        encoding="utf-8",
    )
    (workspace / "inputs.json").write_text(
        json.dumps(
            {
                "canu_workflow.reads": str(
                    workspace / "results" / "wdl_file" / "toy_reads.fastq"
                )
            }
        ),
        encoding="utf-8",
    )

    status = _github2workspace_product_status(
        workspace_root=workspace,
        rounds=[],
        final_decision=SupervisorDecision(decision="stop", reason="done"),
    )

    assert status == "partial"


@pytest.mark.asyncio
async def test_supervisor_worker_runner_github_repo_uses_code_repository_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace" / "20260515"
    workspace.mkdir(parents=True)
    run_dir = workspace / "orchestration_runs" / "run-1"
    (run_dir / "node_traces").mkdir(parents=True)
    (run_dir / "worker_outputs").mkdir(parents=True)
    cached_root = tmp_path / "code_repository"
    cached_repo = cached_root / "CircAST"
    cached_repo.mkdir(parents=True)
    (cached_repo / ".git").mkdir()
    (cached_repo / "README.md").write_text("cached circast", encoding="utf-8")
    node = TaskNode(
        node_id="inspect",
        title="Inspect repository",
        objective="Inspect repository assets",
        capability_bundles=["repo_fetch", "validate"],
        metadata={
            "task_type": "github2workspace",
            "task": "把这个 GitHub 仓库变成可运行 workspace：https://github.com/xiaofengsong/CircAST",
            "run_dir": str(run_dir),
        },
    )

    async def fake_invoke_worker_runnable(*, agent, node, workspace_root):
        return WorkerResult(status="completed", summary="inspect ok")

    monkeypatch.setattr(supervisor_runtime, "_CODE_REPOSITORY_ROOT", cached_root)
    monkeypatch.setattr(
        supervisor_runtime,
        "_invoke_worker_runnable",
        fake_invoke_worker_runnable,
    )
    runner = SupervisorWorkerRunner(base_agent=Mock(), workspace_root=workspace)

    result = await runner.run(node)

    assert result.status == "completed"
    assert (workspace / "CircAST" / ".git").exists()
    assert (workspace / "CircAST" / "README.md").read_text(encoding="utf-8") == "cached circast"
    payload = json.loads((run_dir / "github_repo_materialization.json").read_text(encoding="utf-8"))
    assert payload["selected_strategy"] == "code_repository_copy"


@pytest.mark.asyncio
async def test_invoke_worker_agent_github_repo_prefers_code_repository_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace" / "20260515"
    workspace.mkdir(parents=True)
    run_dir = workspace / "orchestration_runs" / "run-1"
    (run_dir / "node_traces").mkdir(parents=True)
    (run_dir / "worker_outputs").mkdir(parents=True)
    cached_root = tmp_path / "code_repository"
    cached_repo = cached_root / "Graphinity"
    cached_repo.mkdir(parents=True)
    (cached_repo / ".git").mkdir()
    (cached_repo / "README.md").write_text("cached repo", encoding="utf-8")
    node = TaskNode(
        node_id="inspect",
        title="Inspect repository",
        objective="Inspect repository assets",
        capability_bundles=["repo_fetch", "validate"],
        metadata={
            "task_type": "github2workspace",
            "task": "把这个 GitHub 仓库变成可运行 workspace：https://github.com/oxpig/Graphinity",
            "run_dir": str(run_dir),
        },
    )

    async def fake_invoke_worker_runnable(*, agent, node, workspace_root):
        return WorkerResult(status="completed", summary="inspect ok")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess.run should not be used when code_repository cache is available")

    monkeypatch.setattr(supervisor_runtime, "_CODE_REPOSITORY_ROOT", cached_root)
    monkeypatch.setattr(supervisor_runtime.subprocess, "run", fail_if_called)
    monkeypatch.setattr(
        supervisor_runtime,
        "_invoke_worker_runnable",
        fake_invoke_worker_runnable,
    )

    result = await _invoke_worker_agent(
        agent=Mock(),
        node=node,
        workspace_root=workspace,
    )

    assert result.status == "completed"
    assert (workspace / "Graphinity" / ".git").exists()
    assert (workspace / "Graphinity" / "README.md").read_text(encoding="utf-8") == "cached repo"
    payload = json.loads((run_dir / "github_repo_materialization.json").read_text(encoding="utf-8"))
    assert payload["selected_strategy"] == "code_repository_copy"
    assert payload["cached_repo"] == str(cached_repo)


@pytest.mark.asyncio
async def test_invoke_worker_agent_github_repo_falls_back_to_depth_clone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace" / "20260515"
    workspace.mkdir(parents=True)
    run_dir = workspace / "orchestration_runs" / "run-1"
    (run_dir / "node_traces").mkdir(parents=True)
    (run_dir / "worker_outputs").mkdir(parents=True)
    node = TaskNode(
        node_id="inspect",
        title="Inspect repository",
        objective="Inspect repository assets",
        capability_bundles=["repo_fetch", "validate"],
        metadata={
            "task_type": "github2workspace",
            "task": "把这个 GitHub 仓库变成可运行 workspace：https://github.com/oxpig/Graphinity",
            "run_dir": str(run_dir),
        },
    )

    attempted: list[list[str]] = []

    def fake_run(*args, **kwargs):
        command = list(args[0])
        attempted.append(command)
        destination = Path(command[-1])
        if command[:2] == ["git", "clone"] and "--depth" not in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="normal clone failed")
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ".git").mkdir(exist_ok=True)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    async def fake_invoke_worker_runnable(*, agent, node, workspace_root):
        return WorkerResult(status="completed", summary="inspect ok")

    monkeypatch.setattr(supervisor_runtime, "_CODE_REPOSITORY_ROOT", tmp_path / "missing-code-repository")
    monkeypatch.setattr(supervisor_runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(
        supervisor_runtime,
        "_invoke_worker_runnable",
        fake_invoke_worker_runnable,
    )

    result = await _invoke_worker_agent(
        agent=Mock(),
        node=node,
        workspace_root=workspace,
    )

    assert result.status == "completed"
    assert attempted[0] == [
        "git",
        "clone",
        "https://github.com/oxpig/Graphinity.git",
        str(workspace / "Graphinity"),
    ]
    assert attempted[1] == [
        "git",
        "clone",
        "--depth",
        "1",
        "https://github.com/oxpig/Graphinity.git",
        str(workspace / "Graphinity"),
    ]
    payload = json.loads((run_dir / "github_repo_materialization.json").read_text(encoding="utf-8"))
    assert payload["selected_strategy"] == "shallow_clone"


@pytest.mark.asyncio
async def test_invoke_worker_agent_github_repo_falls_back_to_local_clone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace" / "20260515"
    workspace.mkdir(parents=True)
    run_dir = workspace / "orchestration_runs" / "run-1"
    (run_dir / "node_traces").mkdir(parents=True)
    (run_dir / "worker_outputs").mkdir(parents=True)
    local_repo = tmp_path / "Graphinity"
    local_repo.mkdir()
    (local_repo / ".git").mkdir()
    node = TaskNode(
        node_id="inspect",
        title="Inspect repository",
        objective="Inspect repository assets",
        capability_bundles=["repo_fetch", "validate"],
        metadata={
            "task_type": "github2workspace",
            "task": "把这个 GitHub 仓库变成可运行 workspace：https://github.com/oxpig/Graphinity",
            "run_dir": str(run_dir),
        },
    )

    attempted: list[list[str]] = []

    def fake_run(*args, **kwargs):
        command = list(args[0])
        attempted.append(command)
        destination = Path(command[-1])
        if "--local" in command:
            destination.mkdir(parents=True, exist_ok=True)
            (destination / ".git").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="remote clone failed")

    async def fake_invoke_worker_runnable(*, agent, node, workspace_root):
        return WorkerResult(status="completed", summary="inspect ok")

    monkeypatch.setattr(supervisor_runtime, "_CODE_REPOSITORY_ROOT", tmp_path / "missing-code-repository")
    monkeypatch.setattr(supervisor_runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(
        supervisor_runtime,
        "_invoke_worker_runnable",
        fake_invoke_worker_runnable,
    )

    result = await _invoke_worker_agent(
        agent=Mock(),
        node=node,
        workspace_root=workspace,
    )

    assert result.status == "completed"
    assert attempted[-1] == [
        "git",
        "clone",
        "--local",
        "--no-hardlinks",
        str(local_repo),
        str(workspace / "Graphinity"),
    ]
    payload = json.loads((run_dir / "github_repo_materialization.json").read_text(encoding="utf-8"))
    assert payload["selected_strategy"] == "local_clone"
    assert payload["local_repo"] == str(local_repo)


@pytest.mark.asyncio
async def test_invoke_worker_agent_github_repo_returns_failure_when_all_fallbacks_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace" / "20260515"
    workspace.mkdir(parents=True)
    run_dir = workspace / "orchestration_runs" / "run-1"
    (run_dir / "node_traces").mkdir(parents=True)
    (run_dir / "worker_outputs").mkdir(parents=True)
    node = TaskNode(
        node_id="inspect",
        title="Inspect repository",
        objective="Inspect repository assets",
        capability_bundles=["repo_fetch", "validate"],
        metadata={
            "task_type": "github2workspace",
            "task": "把这个 GitHub 仓库变成可运行 workspace：https://github.com/oxpig/Graphinity",
            "run_dir": str(run_dir),
        },
    )

    def fake_run(*args, **kwargs):
        command = list(args[0])
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="clone failed")

    async def fake_invoke_worker_runnable(*, agent, node, workspace_root):
        raise AssertionError("worker runnable should not be invoked when repo materialization fails")

    monkeypatch.setattr(supervisor_runtime, "_CODE_REPOSITORY_ROOT", tmp_path / "missing-code-repository")
    monkeypatch.setattr(supervisor_runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(
        supervisor_runtime,
        "_invoke_worker_runnable",
        fake_invoke_worker_runnable,
    )

    result = await _invoke_worker_agent(
        agent=Mock(),
        node=node,
        workspace_root=workspace,
    )

    assert result.status == "failed"
    assert result.failure_reason == "repo_materialization_failed"
    assert any("clone: failed" in line for line in result.evidence)
    assert any("shallow_clone: failed" in line for line in result.evidence)
    assert any("local_clone: failed" in line for line in result.evidence)
    payload = json.loads((run_dir / "github_repo_materialization.json").read_text(encoding="utf-8"))
    assert payload["selected_strategy"] is None


def test_maybe_prepare_worker_inputs_reuses_successful_github2workspace_wdl_smoke(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260518"
    repo_dir = workspace / "AutoCirc"
    repo_dir.mkdir(parents=True)
    (repo_dir / "autocirc_smoke.wdl").write_text("workflow AutoCircSmokeValidation {}", encoding="utf-8")
    (repo_dir / "autocirc_run.wdl").write_text("workflow AutoCircRun {}", encoding="utf-8")
    (repo_dir / "autocirc_smoke.inputs.json").write_text("{}", encoding="utf-8")

    run_dir = workspace / "orchestration_runs" / "run-1"
    smoke_dir = run_dir / "wdl_smoke_run" / "20260518_014156_AutoCircSmokeValidation"
    smoke_dir.mkdir(parents=True)
    output_file = smoke_dir / "circ.final.bed"
    output_file.write_text("chr1\t1\t2\n", encoding="utf-8")
    (smoke_dir / "outputs.json").write_text(
        json.dumps({"AutoCircSmokeValidation.circ_final_bed": str(output_file)}),
        encoding="utf-8",
    )
    (smoke_dir / "workflow.log").write_text(
        '2026-05-18 NOTICE docker task exit :: state: "complete", exit_code: 0\n',
        encoding="utf-8",
    )

    node = TaskNode(
        node_id="wdl",
        title="Run WDL workflow",
        objective="Generate or repair WDL inputs and run miniwdl workflow validation.",
        capability_bundles=["wdl_run", "validate"],
        metadata={
            "task_type": "github2workspace",
            "task": "把这个 GitHub 仓库变成可运行 workspace：https://github.com/chanzhou/AutoCirc",
            "run_dir": str(run_dir),
        },
    )

    result = supervisor_runtime._maybe_prepare_worker_inputs(
        node=node,
        workspace_root=workspace,
    )

    assert result is not None
    assert result.status == "partial"
    assert "main-function WDL path is not yet verified" in result.summary
    assert str(smoke_dir / "outputs.json") in result.artifacts
    assert str(smoke_dir / "workflow.log") in result.artifacts
    assert str(repo_dir / "autocirc_smoke.wdl") in result.artifacts
    assert str(output_file) in result.artifacts


def test_node_decision_rejects_github2workspace_wdl_without_real_run_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260518"
    repo_dir = workspace / "AQUARIUM-HB"
    repo_dir.mkdir(parents=True)
    (repo_dir / "AQUARIUM_HB.wdl").write_text("workflow AquariumHB {}", encoding="utf-8")

    run_dir = workspace / "orchestration_runs" / "run-1"
    run_dir.mkdir(parents=True)

    node = TaskNode(
        node_id="wdl",
        title="Run WDL workflow",
        objective="Generate or repair WDL inputs and run miniwdl workflow validation.",
        capability_bundles=["wdl_run", "validate"],
        metadata={
            "decision_check": True,
            "task_type": "github2workspace",
            "run_dir": str(run_dir),
        },
    )

    result = WorkerResult(status="completed", summary="wdl ok")
    action, reason = orchestration_runtime._node_decision_action(node=node, result=result)

    assert action == "finalize"
    assert "no successful main-function miniwdl run evidence was found" in reason


def test_node_decision_accepts_github2workspace_wdl_with_real_run_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260518"
    run_dir = workspace / "orchestration_runs" / "run-1"
    workflow_dir = run_dir / "miniwdl_run" / "20260518_043318_CircASTWorkflow"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "outputs.json").write_text(
        json.dumps({"CircASTWorkflow.result": "/tmp/CircAST_result.txt"}),
        encoding="utf-8",
    )
    (workflow_dir / "workflow.log").write_text(
        '2026-05-18 NOTICE docker task exit :: state: "complete", exit_code: 0\n',
        encoding="utf-8",
    )

    node = TaskNode(
        node_id="wdl",
        title="Run WDL workflow",
        objective="Generate or repair WDL inputs and run miniwdl workflow validation.",
        capability_bundles=["wdl_run", "validate"],
        metadata={
            "decision_check": True,
            "task_type": "github2workspace",
            "run_dir": str(run_dir),
        },
    )

    result = WorkerResult(status="completed", summary="wdl ok")
    action, reason = orchestration_runtime._node_decision_action(node=node, result=result)

    assert action == "continue"
    assert reason == "Node outcome is sufficient to continue."


def test_parse_worker_result_extracts_direct_json() -> None:
    result = _parse_worker_result(
        '{"status":"partial","summary":"need inputs","failure_reason":"missing data"}'
    )

    assert result.status == "partial"
    assert result.summary == "need inputs"
    assert result.failure_reason == "missing data"


def test_parse_worker_result_extracts_embedded_json_from_python_repr_list() -> None:
    text = """[
{'id': 'rs_x', 'summary': [], 'type': 'reasoning'},
{'type': 'text', 'text': '{"status":"partial","summary":"registered but not ready","failure_reason":"inputs missing"}'}
]"""

    result = _parse_worker_result(text)

    assert result.status == "partial"
    assert result.summary == "registered but not ready"
    assert result.failure_reason == "inputs missing"


def test_parse_worker_result_preserves_spawned_subgraph() -> None:
    result = _parse_worker_result(
        '{"status":"completed","summary":"registered","spawned_subgraph":{"selected_tools":["canu","Flye"],"dataset_keys":["long-read-ecoli-pacbio"]}}'
    )

    assert result.status == "completed"
    assert result.spawned_subgraph == {
        "selected_tools": ["canu", "Flye"],
        "dataset_keys": ["long-read-ecoli-pacbio"],
    }


def test_last_ai_text_skips_empty_streaming_tool_call_messages() -> None:
    messages = [
        HumanMessage(content="task"),
        AIMessage(content='{"status":"completed","summary":"useful answer"}'),
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "call-1"}]),
        ToolMessage(content="tool result", tool_call_id="call-1"),
    ]

    assert _last_ai_text(messages) == '{"status":"completed","summary":"useful answer"}'


def test_last_ai_text_accepts_ai_message_chunks() -> None:
    messages = [
        HumanMessage(content="task"),
        AIMessageChunk(content='{"status":"completed","summary":"chunk answer"}'),
    ]

    assert _last_ai_text(messages) == '{"status":"completed","summary":"chunk answer"}'


def test_last_ai_text_concatenates_streaming_ai_chunks() -> None:
    messages = [
        HumanMessage(content="task"),
        AIMessageChunk(content='{"status":"completed",'),
        AIMessageChunk(content='"summary":"chunk answer"'),
        AIMessageChunk(content="}"),
    ]

    assert _last_ai_text(messages) == '{"status":"completed","summary":"chunk answer"}'


@pytest.mark.asyncio
async def test_invoke_worker_agent_uses_messages_mode_by_default(
    tmp_path: Path,
) -> None:
    node = TaskNode(
        node_id="analyze_task",
        title="Analyze task",
        objective="Analyze the request",
        capability_bundles=["plan", "validate"],
        metadata={"task": "帮我分析一下这个问题", "task_type": "generic"},
    )
    agent = AsyncMock()
    agent.ainvoke.return_value = {
        "messages": [
            AIMessage(
                content='{"status":"completed","summary":"ok","artifacts":[],"evidence":[]}'
            )
        ]
    }

    await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=tmp_path,
    )

    payload = agent.ainvoke.await_args.args[0]
    messages = payload["messages"]
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert "You are a generic worker node executor." in str(messages[0].content)
    assert isinstance(messages[1], HumanMessage)
    assert "return the required JSON only" in str(messages[1].content)
    assert agent.ainvoke.await_args.kwargs == {}


def test_build_worker_invoke_request_uses_messages_mode_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CODE2WORKSPACE_SUPERVISOR_WORKER_PROMPT_MODE", raising=False)

    payload, kwargs = _build_worker_invoke_request("Worker prompt")

    assert len(payload["messages"]) == 2
    assert isinstance(payload["messages"][0], SystemMessage)
    assert isinstance(payload["messages"][1], HumanMessage)
    assert kwargs == {}


def test_build_worker_invoke_request_uses_context_mode_when_requested(monkeypatch) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_SUPERVISOR_WORKER_PROMPT_MODE", "context")

    payload, kwargs = _build_worker_invoke_request("Worker prompt")

    assert len(payload["messages"]) == 1
    assert isinstance(payload["messages"][0], HumanMessage)
    assert kwargs["context"]["system_prompt"] == "Worker prompt"


@pytest.mark.asyncio
async def test_invoke_worker_agent_retries_transient_errors(
    tmp_path: Path,
) -> None:
    class APIConnectionError(Exception):
        pass

    node = TaskNode(
        node_id="analyze_task",
        title="Analyze task",
        objective="Analyze the request",
        capability_bundles=["plan", "validate"],
        metadata={"task": "帮我分析一下这个问题", "task_type": "generic"},
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = [
        APIConnectionError("Connection error"),
        {
            "messages": [
                AIMessage(
                    content='{"status":"completed","summary":"ok","artifacts":[],"evidence":[]}'
                )
            ]
        },
    ]

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=tmp_path,
    )

    assert result.status == "completed"
    assert agent.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_invoke_worker_agent_records_internal_tool_calls(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-a"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="worker_solution",
        title="Solve",
        objective="Use a tool and answer",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "inspect files",
            "task_type": "generic",
            "run_dir": str(run_dir),
        },
    )
    class _Agent:
        async def ainvoke(self, _payload, **_kwargs):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "read_file",
                                "args": {"file_path": "README.md"},
                                "id": "call_read",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(
                        content="README contents",
                        tool_call_id="call_read",
                        status="success",
                    ),
                    AIMessage(
                        content='{"status":"completed","summary":"done","artifacts":[],"evidence":[]}'
                    ),
                ]
            }

    agent = _Agent()

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=tmp_path,
    )

    assert result.status == "completed"
    activity = (run_dir / "tool_activity.jsonl").read_text(encoding="utf-8")
    assert '"event": "worker_tool_call"' in activity
    assert '"tool_name": "read_file"' in activity
    assert '"args_preview": "{\\"file_path\\": \\"README.md\\"}"' in activity
    assert '"event": "worker_tool_result"' in activity
    assert '"result_preview": "README contents"' in activity


@pytest.mark.asyncio
async def test_invoke_worker_agent_records_raw_worker_trace(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-raw-trace"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="worker_solution",
        title="Solve",
        objective="Use a tool and answer",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": "inspect files",
            "task_type": "generic",
            "run_dir": str(run_dir),
        },
    )

    class _Agent:
        async def ainvoke(self, _payload, **_kwargs):
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "fetch_url",
                                "args": {"url": "https://example.org/source"},
                                "id": "call_fetch",
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(
                        content='{"url":"https://example.org/source","markdown_content":"full source body"}',
                        tool_call_id="call_fetch",
                        status="success",
                    ),
                    AIMessage(
                        content='{"status":"completed","summary":"done","artifacts":[],"evidence":["https://example.org/source"]}',
                        response_metadata={
                            "model_name": "gpt-test",
                            "model_provider": "openai",
                        },
                        usage_metadata={
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "total_tokens": 15,
                        },
                    ),
                ]
            }

    result = await _invoke_worker_agent(
        agent=_Agent(),
        node=node,
        workspace_root=tmp_path,
    )

    assert result.status == "completed"
    trace_path = run_dir / "raw_worker_traces" / "worker_solution.jsonl"
    records = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in records].count("worker_message") == 3
    finished = records[-1]
    assert finished["event"] == "worker_invocation_finished"
    assert finished["model_name"] == "openai:gpt-test"
    assert finished["usage"]["total_tokens"] == 15
    assert finished["parsed_worker_result"]["summary"] == "done"
    assert finished["source_urls"] == ["https://example.org/source"]


@pytest.mark.asyncio
async def test_raw_worker_trace_can_be_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SUPERVISOR_RAW_WORKER_TRACE_ENV, "0")
    run_dir = tmp_path / "orchestration_runs" / "run-raw-trace-disabled"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="worker_solution",
        title="Solve",
        objective="Answer",
        capability_bundles=["summarize"],
        metadata={"task": "hello", "task_type": "generic", "run_dir": str(run_dir)},
    )

    class _Agent:
        async def ainvoke(self, _payload, **_kwargs):
            return {
                "messages": [
                    AIMessage(content='{"status":"completed","summary":"done"}'),
                ]
            }

    result = await _invoke_worker_agent(
        agent=_Agent(),
        node=node,
        workspace_root=tmp_path,
    )

    assert result.status == "completed"
    assert not (run_dir / "raw_worker_traces").exists()


@pytest.mark.asyncio
async def test_invoke_worker_agent_streams_internal_tool_calls_before_completion(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-streaming"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="build",
        title="Build",
        objective="Use a tool before finishing",
        capability_bundles=["docker_build_run", "validate"],
        metadata={
            "task": "build files",
            "task_type": "github2workspace",
            "run_dir": str(run_dir),
        },
    )

    class _StreamingAgent:
        def __init__(self) -> None:
            self.first_call_written = asyncio.Event()
            self.allow_finish = asyncio.Event()

        def astream(self, _payload, **_kwargs):
            async def _gen():
                yield (
                    (),
                    "messages",
                    (
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "read_file",
                                    "args": {"file_path": "README.md"},
                                    "id": "call_read",
                                    "type": "tool_call",
                                }
                            ],
                        ),
                        {},
                    ),
                )
                self.first_call_written.set()
                await self.allow_finish.wait()
                yield (
                    (),
                    "messages",
                    (
                        ToolMessage(
                            content="README contents",
                            tool_call_id="call_read",
                            status="success",
                        ),
                        {},
                    ),
                )
                yield (
                    (),
                    "messages",
                    (
                        AIMessage(
                            content='{"status":"completed","summary":"done","artifacts":[],"evidence":[]}'
                        ),
                        {},
                    ),
                )

            return _gen()

        async def ainvoke(self, _payload, **_kwargs):
            raise AssertionError("streaming path should be used")

    agent = _StreamingAgent()
    task = asyncio.create_task(
        _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=tmp_path,
        )
    )

    await asyncio.wait_for(agent.first_call_written.wait(), timeout=1)
    activity = (run_dir / "tool_activity.jsonl").read_text(encoding="utf-8")
    assert '"event": "worker_tool_call"' in activity
    assert '"tool_name": "read_file"' in activity
    assert not task.done()

    agent.allow_finish.set()
    result = await asyncio.wait_for(task, timeout=1)

    assert result.status == "completed"
    final_activity = (run_dir / "tool_activity.jsonl").read_text(encoding="utf-8")
    assert '"event": "worker_tool_result"' in final_activity


@pytest.mark.asyncio
async def test_supervisor_worker_runner_prefers_worker_subagent(
    tmp_path: Path,
) -> None:
    node = TaskNode(
        node_id="worker_solution",
        title="Solve",
        objective="Solve the request",
        capability_bundles=["summarize", "validate"],
        metadata={"task": "hello", "task_type": "generic"},
    )
    base_agent = AsyncMock()
    worker_agent = AsyncMock()
    worker_agent.ainvoke.return_value = {
        "messages": [
            AIMessage(
                content='{"status":"completed","summary":"from worker subagent","artifacts":[],"evidence":[]}'
            )
        ]
    }
    runner = SupervisorWorkerRunner(
        base_agent=base_agent,
        default_subagent=worker_agent,
        workspace_root=tmp_path,
    )

    result = await runner.run(node)

    assert result.status == "completed"
    assert result.summary == "from worker subagent"
    worker_agent.ainvoke.assert_awaited_once()
    base_agent.ainvoke.assert_not_called()


def test_build_benchmark_comparison_handles_mixed_metric_winners() -> None:
    comparison = _build_benchmark_comparison(
        [
            {
                "repo": "megahit",
                "success": True,
                "metrics": {
                    "contig_count": 472,
                    "assembly_size": 4530520,
                    "n50": 18360,
                },
            },
            {
                "repo": "spades",
                "success": True,
                "metrics": {
                    "contig_count": 1191,
                    "assembly_size": 4582516,
                    "n50": 24099,
                },
            },
        ]
    )

    assert comparison == {
        "best_n50": "spades",
        "lowest_contig_count": "megahit",
        "largest_assembly_size": "spades",
        "overall": (
            "Overall favors spades by N50/assembly-size strength, "
            "while megahit has the lower contig_count."
        ),
    }


@pytest.mark.asyncio
async def test_invoke_worker_agent_uses_deterministic_benchmark_register_helper(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-1"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "在本地 benchmark 目录里只选择 spades 和 megahit，先完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": ["spades", "megahit"],
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("register helper path should bypass the model")

    def fake_register_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "resolve-datasets":
            (run_dir / "dataset_resolution.json").write_text("{}", encoding="utf-8")
            (run_dir / "dataset_resolution.md").write_text("# datasets\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {}}
        if phase == "init":
            (run_dir / "benchmark_plan.json").write_text("{}", encoding="utf-8")
            (run_dir / "benchmark_plan.md").write_text("# plan\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"case_order": ["spades", "megahit"]}}
        repo = phase.split(":", 1)[1]
        case_dir = run_dir / "cases" / repo
        case_dir.mkdir(parents=True, exist_ok=True)
        if phase.startswith("prepare-case:"):
            (case_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "dataset_key": "short-read-ecoli-srr001666",
                        "metric_keys": ["contig_count", "assembly_size", "n50"],
                        "selected_input_files": {"reads_1": "/tmp/r1", "reads_2": "/tmp/r2"},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "dataset_selection.json").write_text("{}", encoding="utf-8")
            (case_dir / "dataset_manifest.json").write_text("{}", encoding="utf-8")
            (case_dir / "agent_task.md").write_text("# task\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": repo}}
        if phase.startswith("execution-ready:"):
            (case_dir / "execution_ready.json").write_text(
                json.dumps(
                    {
                        "ready": True,
                        "runtime_image": f"benchmark/{repo}",
                        "wdl_path": f"/tmp/{repo}.wdl",
                        "inputs_json_path": f"/tmp/{repo}.json",
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": repo}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_register_helper):
        result = await _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "completed"
    assert "spades" in result.summary
    assert result.spawned_subgraph == {
        "selected_tools": ["spades", "megahit"],
        "ready_tools": ["spades", "megahit"],
        "blocked_tools": [],
        "dataset_keys": ["short-read-ecoli-srr001666"],
        "register_report": str(run_dir / "register_report.json"),
    }
    assert (run_dir / "benchmark_plan.json").exists()
    assert (run_dir / "dataset_resolution.json").exists()
    assert (run_dir / "metric_plan.json").exists()
    assert (run_dir / "cases" / "spades" / "execution_ready.json").exists()
    assert (run_dir / "cases" / "megahit" / "execution_ready.json").exists()
    operator_store = OperatorStore(workspace_root / "operator_store")
    rows = operator_store.search(OperatorSearchFilter(input_media_type="file", status="registered_ready"))
    assert {row["name"] for row in rows} == {"spades", "megahit"}
    assert (
        workspace_root
        / "operator_store"
        / "objects"
        / "benchmark"
        / "spades"
        / "run-1"
        / "operator_product.json"
    ).exists()


@pytest.mark.asyncio
async def test_benchmark_register_partial_returns_only_ready_tools_for_fanout(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-partial"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "在本地 circRNA benchmark 目录里选择多个工具。",
            "run_dir": str(run_dir),
            "selected_tools": ["ACValidator", "AQUARIUM-HB"],
        },
    )

    def fake_register_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "resolve-datasets":
            (run_dir / "dataset_resolution.json").write_text("{}", encoding="utf-8")
            (run_dir / "dataset_resolution.md").write_text("# datasets\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {}}
        if phase == "init":
            (run_dir / "benchmark_plan.json").write_text("{}", encoding="utf-8")
            (run_dir / "benchmark_plan.md").write_text("# plan\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"case_order": ["ACValidator", "AQUARIUM-HB"]}}
        repo = phase.split(":", 1)[1]
        case_dir = run_dir / "cases" / repo
        case_dir.mkdir(parents=True, exist_ok=True)
        if phase.startswith("prepare-case:"):
            (case_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "dataset_key": "circrna-test",
                        "metric_keys": [],
                        "selected_input_files": {"input_1": "/tmp/input"},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "dataset_selection.json").write_text("{}", encoding="utf-8")
            (case_dir / "dataset_manifest.json").write_text("{}", encoding="utf-8")
            (case_dir / "agent_task.md").write_text("# task\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": repo}}
        if phase.startswith("execution-ready:"):
            ready = repo == "ACValidator"
            (case_dir / "execution_ready.json").write_text(
                json.dumps(
                    {
                        "ready": ready,
                        "runtime_image": "benchmark/acvalidator" if ready else None,
                        "wdl_path": f"/tmp/{repo}.wdl",
                        "inputs_json_path": f"/tmp/{repo}.json",
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": repo}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_register_helper):
        result = await _invoke_worker_agent(
            agent=AsyncMock(),
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "partial"
    assert result.failure_reason == "execution_ready_incomplete"
    assert result.spawned_subgraph == {
        "selected_tools": ["ACValidator"],
        "registered_tools": ["ACValidator", "AQUARIUM-HB"],
        "ready_tools": ["ACValidator"],
        "blocked_tools": ["AQUARIUM-HB"],
        "dataset_keys": ["circrna-test"],
        "register_report": str(run_dir / "register_report.json"),
    }


@pytest.mark.asyncio
async def test_benchmark_register_rejects_tools_that_violate_exclusions(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-exclude"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "并行跑多个算子，但不要选 spades 和 megahit。",
            "run_dir": str(run_dir),
            "selected_tools": ["spades", "megahit"],
            "excluded_tools": ["spades", "megahit"],
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("register helper path should bypass the model")

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "failed"
    assert result.failure_reason == "selected_tools_violate_exclusion_constraint"
    assert "spades" in result.summary
    assert "megahit" in result.summary


@pytest.mark.asyncio
async def test_benchmark_register_fails_fast_when_no_tools_remain_after_exclusion(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-empty"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "不要选 spades 和 megahit。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": ["spades", "megahit"],
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("empty register case should still bypass the model")

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "failed"
    assert result.failure_reason == "missing_selected_tools"


@pytest.mark.asyncio
async def test_benchmark_register_reports_url_only_assets_missing(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-url-only"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "https://github.com/example/tool-a\nhttps://github.com/example/tool-b\n请选择共享数据集做 benchmark。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": None,
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("URL-only register should still bypass the model")

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "failed"
    assert result.failure_reason == "missing_benchmark_assets"
    assert result.next_action_hint == "prepare_benchmark_assets_from_urls"
    assert "URL-only benchmark requests" in result.summary


@pytest.mark.asyncio
async def test_benchmark_register_selects_tools_from_operator_store_by_query_and_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE2WORKSPACE_OPERATOR_STORE_EMBEDDINGS_ENABLED", "0")
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-operator-search"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "immune-escape"
    benchmark_root.mkdir(parents=True)
    autodock_wdl = tmp_path / "autodock-vina.wdl"
    autodock_inputs = tmp_path / "autodock-vina.inputs.json"
    autodock_docker = tmp_path / "AutoDock-Vina.Dockerfile"
    receptor = tmp_path / "receptor.pdbqt"
    ligand = tmp_path / "ligand.pdbqt"
    autodock_wdl.write_text("workflow AutoDockVinaWorkflow {}", encoding="utf-8")
    autodock_inputs.write_text("{}", encoding="utf-8")
    autodock_docker.write_text("FROM scratch\n", encoding="utf-8")
    receptor.write_text("RECEPTOR", encoding="utf-8")
    ligand.write_text("LIGAND", encoding="utf-8")

    store = OperatorStore(workspace_root / "operator_store")
    store.write_manifest(
        {
            "product_id": "github2workspace:AutoDock-Vina:test",
            "operator_id": "github2workspace:AutoDock-Vina",
            "name": "AutoDock-Vina",
            "family": "github2workspace",
            "version": "test",
            "status": "completed",
            "summary": "Immune escape docking workflow for receptor ligand structural bundle.",
            "created_at": "2026-05-15T00:00:00Z",
            "source": {
                "repo_url": "https://github.com/ccsb-scripps/AutoDock-Vina",
                "repo_name": "AutoDock-Vina",
                "commit": "",
            },
            "runtime": {
                "backend": "wdl",
                "image_ref": "AutoDock-Vina",
                "workflow_path": str(autodock_wdl),
                "inputs_json_path": str(autodock_inputs),
                "dockerfile_path": str(autodock_docker),
            },
            "inputs": [
                {"name": "receptor_file", "media_type": "pdbqt", "path": str(receptor), "schema_path": "", "required": True},
                {"name": "ligand_file", "media_type": "pdbqt", "path": str(ligand), "schema_path": "", "required": True},
            ],
            "outputs": [
                {"name": "docked_output", "media_type": "pdbqt", "path": "/tmp/out.pdbqt", "schema_path": "", "required": False}
            ],
            "metrics": [],
            "validation": {
                "validation_id": "github2workspace:test:AutoDock-Vina",
                "status": "completed",
                "dataset_id": "immune-escape-covabdab-structural-bundle",
                "run_dir": str(run_dir),
                "summary": "completed",
                "created_at": "2026-05-15T00:00:00Z",
            },
            "tags": ["github2workspace", "completed", "domain:immune-escape", "wdl-completed"],
        }
    )
    store.write_manifest(
        {
            "product_id": "github2workspace:esm:test",
            "operator_id": "github2workspace:esm",
            "name": "esm",
            "family": "github2workspace",
            "version": "test",
            "status": "completed",
            "summary": "Protein language model scoring workflow for immune escape sequence variants.",
            "created_at": "2026-05-15T00:00:00Z",
            "source": {
                "repo_url": "https://github.com/facebookresearch/esm",
                "repo_name": "esm",
                "commit": "",
            },
            "runtime": {
                "backend": "wdl",
                "image_ref": "esm",
                "workflow_path": str(tmp_path / "esm.wdl"),
                "inputs_json_path": str(tmp_path / "esm.inputs.json"),
                "dockerfile_path": str(tmp_path / "esm.Dockerfile"),
            },
            "inputs": [
                {"name": "input_fasta", "media_type": "fasta", "path": str(tmp_path / "proteins.fasta"), "schema_path": "", "required": True}
            ],
            "outputs": [
                {"name": "scores", "media_type": "json", "path": "/tmp/scores.json", "schema_path": "", "required": False}
            ],
            "metrics": [],
            "validation": {
                "validation_id": "github2workspace:test:esm",
                "status": "completed",
                "dataset_id": "immune-escape-covabdab-structural-bundle",
                "run_dir": str(run_dir),
                "summary": "completed",
                "created_at": "2026-05-15T00:00:00Z",
            },
            "tags": ["github2workspace", "completed", "domain:immune-escape", "wdl-completed"],
        }
    )

    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在 immune-escape-covabdab-structural-bundle 数据集里选择适合做 vina docking、并且输入是 receptor/ligand pdbqt 的算子并完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    (tmp_path / "esm.wdl").write_text("workflow ESMWorkflow {}", encoding="utf-8")
    (tmp_path / "esm.inputs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "esm.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "proteins.fasta").write_text(">p\nAAAA\n", encoding="utf-8")

    result = await _invoke_worker_agent(
        agent=AsyncMock(),
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    assert result.spawned_subgraph == {
        "selected_tools": ["AutoDock-Vina"],
        "ready_tools": ["AutoDock-Vina"],
        "blocked_tools": [],
        "dataset_keys": ["immune-escape-covabdab-structural-bundle"],
        "register_report": str(run_dir / "register_report.json"),
    }
    selection_report = json.loads((run_dir / "operator_selection.json").read_text(encoding="utf-8"))
    assert selection_report["selection_strategy"] == "operator_store_search"
    assert selection_report["selected_tools"] == ["AutoDock-Vina"]
    assert selection_report["dataset_key"] == "immune-escape-covabdab-structural-bundle"
    assert selection_report["selected_operators"][0]["workflow_path"] == str(autodock_wdl)
    assert (run_dir / "cases" / "AutoDock-Vina" / "wdl" / "inputs.json").exists()


@pytest.mark.asyncio
async def test_benchmark_register_defaults_to_max_shared_dataset_tool_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-shared-group-default"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "viral-assembly"
    benchmark_root.mkdir(parents=True)
    pacbio_reads = tmp_path / "pacbio.fastq"
    short_r1 = tmp_path / "R1.fastq.gz"
    short_r2 = tmp_path / "R2.fastq.gz"
    pacbio_reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    short_r1.write_text("R1", encoding="utf-8")
    short_r2.write_text("R2", encoding="utf-8")
    for name in ("flye", "canu", "spades"):
        (tmp_path / f"{name}.wdl").write_text(f"workflow {name.title()}Workflow {{}}", encoding="utf-8")
        (tmp_path / f"{name}.inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / f"{name}.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在该 long read assembly benchmark 数据上选择合适算子并完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "Flye",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Long-read assembler for PacBio datasets.",
                "canonical_text": "long read assembly pacbio hifi assembler",
                "input_media_types": ["fastq"],
                "output_media_types": ["fasta", "gfa"],
                "tags": ["wdl-completed", "domain:covid-assembly"],
                "workflow_path": str(tmp_path / "flye.wdl"),
                "inputs_json_path": str(tmp_path / "flye.inputs.json"),
                "dockerfile_path": str(tmp_path / "flye.Dockerfile"),
                "runtime_image": "Flye",
                "entry_workflow": "FlyeWorkflow",
                "inputs": [
                    {"name": "reads_fastq", "path": str(pacbio_reads), "media_type": "fastq"},
                    {"name": "inputs.json", "path": str(tmp_path / "flye.inputs.json"), "media_type": "json"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 95,
                "rank": 0,
            },
            {
                "name": "canu",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Long-read assembler for PacBio datasets.",
                "canonical_text": "long read assembly pacbio assembler",
                "input_media_types": ["fastq"],
                "output_media_types": ["fasta"],
                "tags": ["wdl-completed", "domain:covid-assembly"],
                "workflow_path": str(tmp_path / "canu.wdl"),
                "inputs_json_path": str(tmp_path / "canu.inputs.json"),
                "dockerfile_path": str(tmp_path / "canu.Dockerfile"),
                "runtime_image": "canu",
                "entry_workflow": "CanuWorkflow",
                "inputs": [
                    {"name": "reads_fastq", "path": str(pacbio_reads), "media_type": "fastq"},
                    {"name": "inputs.json", "path": str(tmp_path / "canu.inputs.json"), "media_type": "json"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 90,
                "rank": 1,
            },
            {
                "name": "spades",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Short-read assembler.",
                "canonical_text": "short read paired-end assembly",
                "input_media_types": ["fastq-gzip"],
                "output_media_types": ["fasta"],
                "tags": ["wdl-completed", "domain:covid-assembly"],
                "workflow_path": str(tmp_path / "spades.wdl"),
                "inputs_json_path": str(tmp_path / "spades.inputs.json"),
                "dockerfile_path": str(tmp_path / "spades.Dockerfile"),
                "runtime_image": "spades",
                "entry_workflow": "SpadesWorkflow",
                "inputs": [
                    {"name": "read1", "path": str(short_r1), "media_type": "fastq-gzip"},
                    {"name": "read2", "path": str(short_r2), "media_type": "fastq-gzip"},
                    {"name": "inputs.json", "path": str(tmp_path / "spades.inputs.json"), "media_type": "json"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 60,
                "rank": 2,
            },
        ],
    )

    result = await _invoke_worker_agent(
        agent=AsyncMock(),
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    assert result.spawned_subgraph == {
        "selected_tools": ["Flye", "canu"],
        "ready_tools": ["Flye", "canu"],
        "blocked_tools": [],
        "dataset_keys": [],
        "register_report": str(run_dir / "register_report.json"),
    }
    selection_report = json.loads((run_dir / "operator_selection.json").read_text(encoding="utf-8"))
    assert selection_report["selection_strategy"] == "operator_store_search"
    assert selection_report["selected_tools"] == ["Flye", "canu"]


@pytest.mark.asyncio
async def test_benchmark_register_can_use_agent_to_choose_from_operator_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-agentic-register"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "immune-escape"
    benchmark_root.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在 immune-escape-covabdab-structural-bundle 数据集里选择适合做 vina docking、并且输入是 receptor/ligand pdbqt 的算子并完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "AutoDock-Vina",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Immune escape docking workflow for receptor ligand structural bundle.",
                "canonical_text": "vina docking receptor ligand pdbqt",
                "input_media_types": ["pdbqt"],
                "output_media_types": ["pdbqt"],
                "tags": ["wdl-completed", "domain:immune-escape"],
                "workflow_path": str(tmp_path / "autodock.wdl"),
                "inputs_json_path": str(tmp_path / "autodock.inputs.json"),
                "dockerfile_path": str(tmp_path / "AutoDock-Vina.Dockerfile"),
                "runtime_image": "AutoDock-Vina",
                "entry_workflow": "AutoDockVinaWorkflow",
                "inputs": [
                    {"name": "receptor_file", "path": str(tmp_path / "receptor.pdbqt")},
                    {"name": "ligand_file", "path": str(tmp_path / "ligand.pdbqt")},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 88,
                "rank": 0,
            },
            {
                "name": "esm",
                "family": "benchmark",
                "validation_status": "completed",
                "summary": "Protein language model scoring workflow for immune escape sequence variants.",
                "canonical_text": "protein language model fasta scoring",
                "input_media_types": ["fasta"],
                "output_media_types": ["json"],
                "tags": ["execution-ready", "domain:immune-escape"],
                "workflow_path": str(tmp_path / "esm.wdl"),
                "inputs_json_path": str(tmp_path / "esm.inputs.json"),
                "dockerfile_path": str(tmp_path / "esm.Dockerfile"),
                "runtime_image": "esm",
                "entry_workflow": "ESMWorkflow",
                "inputs": [],
                "outputs": [],
                "expected_outputs": [],
                "score": 72,
                "rank": 1,
            },
        ],
    )
    (tmp_path / "autodock.wdl").write_text("workflow AutoDockVinaWorkflow {}", encoding="utf-8")
    (tmp_path / "autodock.inputs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AutoDock-Vina.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "receptor.pdbqt").write_text("R", encoding="utf-8")
    (tmp_path / "ligand.pdbqt").write_text("L", encoding="utf-8")
    (tmp_path / "esm.wdl").write_text("workflow ESMWorkflow {}", encoding="utf-8")
    (tmp_path / "esm.inputs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "esm.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    agent = AsyncMock()
    agent.ainvoke.return_value = {
        "messages": [
            AIMessage(
                content='{"selected_tools":["AutoDock-Vina"],"selection_rationale":"docking request and pdbqt inputs match AutoDock-Vina best."}'
            )
        ]
    }
    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    assert agent.ainvoke.await_count == 1
    selection_report = json.loads((run_dir / "operator_selection.json").read_text(encoding="utf-8"))
    assert selection_report["selection_strategy"] == "agent_operator_store_search"
    assert selection_report["selected_tools"] == ["AutoDock-Vina"]
    assert "pdbqt" in selection_report["agent_selection_rationale"]
    assert (run_dir / "cases" / "AutoDock-Vina" / "execution_ready.json").exists()


@pytest.mark.asyncio
async def test_benchmark_register_agent_expands_to_shared_dataset_group_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-agentic-shared-group"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "viral-assembly"
    benchmark_root.mkdir(parents=True)
    pacbio_reads = tmp_path / "pacbio.fastq"
    pacbio_reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    for name in ("flye", "canu"):
        (tmp_path / f"{name}.wdl").write_text(f"workflow {name.title()}Workflow {{}}", encoding="utf-8")
        (tmp_path / f"{name}.inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / f"{name}.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在该 long read assembly benchmark 数据上选择合适算子并完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "Flye",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Long-read assembler for PacBio datasets.",
                "canonical_text": "long read assembly pacbio hifi assembler",
                "input_media_types": ["fastq"],
                "output_media_types": ["fasta", "gfa"],
                "tags": ["wdl-completed", "domain:covid-assembly"],
                "workflow_path": str(tmp_path / "flye.wdl"),
                "inputs_json_path": str(tmp_path / "flye.inputs.json"),
                "dockerfile_path": str(tmp_path / "flye.Dockerfile"),
                "runtime_image": "Flye",
                "entry_workflow": "FlyeWorkflow",
                "inputs": [
                    {"name": "reads_fastq", "path": str(pacbio_reads), "media_type": "fastq"},
                    {"name": "inputs.json", "path": str(tmp_path / "flye.inputs.json"), "media_type": "json"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 95,
                "rank": 0,
            },
            {
                "name": "canu",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Long-read assembler for PacBio datasets.",
                "canonical_text": "long read assembly pacbio assembler",
                "input_media_types": ["fastq"],
                "output_media_types": ["fasta"],
                "tags": ["wdl-completed", "domain:covid-assembly"],
                "workflow_path": str(tmp_path / "canu.wdl"),
                "inputs_json_path": str(tmp_path / "canu.inputs.json"),
                "dockerfile_path": str(tmp_path / "canu.Dockerfile"),
                "runtime_image": "canu",
                "entry_workflow": "CanuWorkflow",
                "inputs": [
                    {"name": "reads_fastq", "path": str(pacbio_reads), "media_type": "fastq"},
                    {"name": "inputs.json", "path": str(tmp_path / "canu.inputs.json"), "media_type": "json"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 90,
                "rank": 1,
            },
        ],
    )
    agent = AsyncMock()
    agent.ainvoke.return_value = {
        "messages": [
            AIMessage(
                content='{"selected_tools":["Flye"],"selection_rationale":"Flye is a strong long-read assembly choice."}'
            )
        ]
    }

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    assert agent.ainvoke.await_count == 1
    selection_report = json.loads((run_dir / "operator_selection.json").read_text(encoding="utf-8"))
    assert selection_report["selection_strategy"] == "agent_operator_store_search"
    assert selection_report["default_preferred_tools"] == ["Flye", "canu"]
    assert selection_report["selected_tools"] == ["Flye", "canu"]


def test_benchmark_candidate_allows_partial_wdl_completed_operator(
    tmp_path: Path,
) -> None:
    operator_path = tmp_path / "aquarium.operator.json"
    payload = {
        "name": "AQUARIUM-HB",
        "family": "github2workspace",
        "validation_status": "partial",
        "summary": "circRNA detector with paired-end FASTQ and reference inputs.",
        "canonical_text": "circRNA detect paired-end fastq fasta gtf",
        "input_media_types": ["fastq-gzip", "fasta", "gtf"],
        "output_media_types": ["report", "sam"],
        "tags": ["github2workspace", "partial", "domain:circrna", "wdl-completed"],
    }

    candidate = supervisor_runtime._benchmark_candidate_from_operator_payload(
        payload=payload,
        operator_path=operator_path,
        excluded_tools=set(),
    )

    assert candidate is not None
    assert candidate["name"] == "AQUARIUM-HB"
    assert candidate["_score"] >= 1


@pytest.mark.asyncio
async def test_benchmark_register_defaults_to_shared_group_with_partial_wdl_ready_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-circrna-shared-group"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "circrna"
    benchmark_root.mkdir(parents=True)
    shared_fastq1 = tmp_path / "sample_1.fastq.gz"
    shared_fastq2 = tmp_path / "sample_2.fastq.gz"
    shared_fasta = tmp_path / "genome.fa"
    shared_gtf = tmp_path / "genes.gtf"
    shared_fastq1.write_text("R1", encoding="utf-8")
    shared_fastq2.write_text("R2", encoding="utf-8")
    shared_fasta.write_text(">chr1\nACGT\n", encoding="utf-8")
    shared_gtf.write_text("chr1\tsrc\texon\t1\t4\t.\t+\t.\tgene_id \"g1\";\n", encoding="utf-8")
    for name in ("circompara2", "aquarium"):
        (tmp_path / f"{name}.wdl").write_text(f"workflow {name.title()}Workflow {{}}", encoding="utf-8")
        (tmp_path / f"{name}.inputs.json").write_text("{}", encoding="utf-8")
        (tmp_path / f"{name}.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在该 circRNA benchmark 数据上优先使用共享数据集并尽可能多选择满足要求的算子。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "circompara2",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "circRNA benchmark workflow on paired-end reads with reference FASTA and GTF.",
                "canonical_text": "circRNA paired-end fastq fasta gtf benchmark",
                "input_media_types": ["fastq-gzip", "fasta", "gtf", "json"],
                "output_media_types": ["report"],
                "tags": ["wdl-completed", "domain:circrna"],
                "workflow_path": str(tmp_path / "circompara2.wdl"),
                "inputs_json_path": str(tmp_path / "circompara2.inputs.json"),
                "dockerfile_path": str(tmp_path / "circompara2.Dockerfile"),
                "runtime_image": "circompara2",
                "entry_workflow": "Circompara2Workflow",
                "inputs": [
                    {"name": "fastq1", "path": str(shared_fastq1), "media_type": "fastq-gzip"},
                    {"name": "fastq2", "path": str(shared_fastq2), "media_type": "fastq-gzip"},
                    {"name": "reference_fasta", "path": str(shared_fasta), "media_type": "fasta"},
                    {"name": "reference_gtf", "path": str(shared_gtf), "media_type": "gtf"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 95,
                "rank": 0,
            },
            {
                "name": "AQUARIUM-HB",
                "family": "github2workspace",
                "validation_status": "partial",
                "summary": "circRNA detection workflow on paired-end reads with reference FASTA and GTF.",
                "canonical_text": "circRNA detect paired-end fastq fasta gtf benchmark",
                "input_media_types": ["fastq-gzip", "fasta", "gtf", "json", "bwt", "pac", "ann", "amb", "sa"],
                "output_media_types": ["report", "sam"],
                "tags": ["wdl-completed", "domain:circrna", "partial"],
                "workflow_path": str(tmp_path / "aquarium.wdl"),
                "inputs_json_path": str(tmp_path / "aquarium.inputs.json"),
                "dockerfile_path": str(tmp_path / "aquarium.Dockerfile"),
                "runtime_image": "AQUARIUM-HB",
                "entry_workflow": "AquariumWorkflow",
                "inputs": [
                    {"name": "fastq1", "path": str(shared_fastq1), "media_type": "fastq-gzip"},
                    {"name": "fastq2", "path": str(shared_fastq2), "media_type": "fastq-gzip"},
                    {"name": "reference_fasta", "path": str(shared_fasta), "media_type": "fasta"},
                    {"name": "reference_gtf", "path": str(shared_gtf), "media_type": "gtf"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 60,
                "rank": 1,
            },
        ],
    )

    result = await _invoke_worker_agent(
        agent=AsyncMock(),
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    selection_report = json.loads((run_dir / "operator_selection.json").read_text(encoding="utf-8"))
    assert selection_report["selected_tools"] == ["circompara2", "AQUARIUM-HB"]
    selected_operator_names = {
        str(item.get("name", ""))
        for item in selection_report["selected_operators"]
        if isinstance(item, dict)
    }
    assert selected_operator_names == {"circompara2", "AQUARIUM-HB"}


@pytest.mark.asyncio
async def test_benchmark_register_prefers_local_benchmark_case_workflow_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-local-case-override"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "circrna"
    case_dir = benchmark_root / "AQUARIUM-HB"
    case_dir.mkdir(parents=True)
    (case_dir / "workflow.wdl").write_text("workflow LocalAquariumWorkflow {}\n", encoding="utf-8")
    (case_dir / "Dockerfile").write_text("FROM localcase\n", encoding="utf-8")
    imported_wdl = tmp_path / "imported_aquarium.wdl"
    imported_inputs = tmp_path / "imported_aquarium.inputs.json"
    imported_dockerfile = tmp_path / "imported_aquarium.Dockerfile"
    imported_wdl.write_text("workflow ImportedAquariumWorkflow {}\n", encoding="utf-8")
    imported_inputs.write_text("{}", encoding="utf-8")
    imported_dockerfile.write_text("FROM imported\n", encoding="utf-8")

    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在该 circRNA benchmark 数据上完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "AQUARIUM-HB",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "circRNA workflow.",
                "canonical_text": "circRNA benchmark",
                "input_media_types": ["fastq-gzip", "fasta", "gtf"],
                "output_media_types": ["report"],
                "tags": ["wdl-completed", "domain:circrna"],
                "workflow_path": str(imported_wdl),
                "inputs_json_path": str(imported_inputs),
                "dockerfile_path": str(imported_dockerfile),
                "runtime_image": "AQUARIUM-HB",
                "entry_workflow": "ImportedAquariumWorkflow",
                "inputs": [],
                "outputs": [],
                "expected_outputs": [],
                "score": 50,
                "rank": 0,
            }
        ],
    )

    result = await _invoke_worker_agent(
        agent=AsyncMock(),
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    staged_wdl = run_dir / "cases" / "AQUARIUM-HB" / "wdl" / "workflow.wdl"
    assert staged_wdl.exists()
    assert "LocalAquariumWorkflow" in staged_wdl.read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "cases" / "AQUARIUM-HB" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["selected_input_source"] == "benchmark_root_case_artifacts"
    assert manifest["source_case_dir"] == str(case_dir)


@pytest.mark.asyncio
async def test_benchmark_register_sanitizes_comment_keys_from_staged_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-sanitize-inputs"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "circrna"
    benchmark_root.mkdir(parents=True)
    imported_wdl = tmp_path / "aquarium.wdl"
    imported_inputs = tmp_path / "aquarium.inputs.json"
    imported_dockerfile = tmp_path / "aquarium.Dockerfile"
    imported_wdl.write_text("workflow AquariumWorkflow {}\n", encoding="utf-8")
    imported_inputs.write_text(
        json.dumps(
            {
                "AQUARIUM_HB_Workflow.mode": "detect",
                "_comment1": "placeholder comment",
                "nested": {"comment2": "keep me", "_comment2": "drop me"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    imported_dockerfile.write_text("FROM imported\n", encoding="utf-8")

    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请完成 circRNA benchmark register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "AQUARIUM-HB",
                "family": "github2workspace",
                "validation_status": "partial",
                "summary": "circRNA workflow.",
                "canonical_text": "circRNA benchmark",
                "input_media_types": ["json"],
                "output_media_types": ["report"],
                "tags": ["wdl-completed", "domain:circrna"],
                "workflow_path": str(imported_wdl),
                "inputs_json_path": str(imported_inputs),
                "dockerfile_path": str(imported_dockerfile),
                "runtime_image": "AQUARIUM-HB",
                "entry_workflow": "AquariumWorkflow",
                "inputs": [],
                "outputs": [],
                "expected_outputs": [],
                "score": 50,
                "rank": 0,
            }
        ],
    )

    result = await _invoke_worker_agent(
        agent=AsyncMock(),
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    staged_inputs = json.loads(
        (run_dir / "cases" / "AQUARIUM-HB" / "wdl" / "inputs.json").read_text(encoding="utf-8")
    )
    assert "_comment1" not in staged_inputs
    assert "_comment2" not in staged_inputs["nested"]
    assert staged_inputs["nested"]["comment2"] == "keep me"


@pytest.mark.asyncio
async def test_benchmark_register_hydrates_placeholder_paths_from_selected_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-hydrate-inputs"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "circrna"
    benchmark_root.mkdir(parents=True)
    imported_wdl = tmp_path / "aquarium.wdl"
    imported_inputs = tmp_path / "aquarium.inputs.json"
    imported_dockerfile = tmp_path / "aquarium.Dockerfile"
    fastq1 = tmp_path / "sample_A_1.fastq.gz"
    fastq2 = tmp_path / "sample_A_2.fastq.gz"
    fasta = tmp_path / "genome.fa"
    gtf = tmp_path / "genes.gtf"
    sa = tmp_path / "genome.fa.sa"
    for path, text in (
        (fastq1, "R1"),
        (fastq2, "R2"),
        (fasta, ">chr1\nACGT\n"),
        (gtf, "chr1\tsrc\texon\t1\t4\t.\t+\t.\tgene_id \"g1\";\n"),
        (sa, "sa"),
    ):
        path.write_text(text, encoding="utf-8")
    imported_wdl.write_text("workflow AquariumWorkflow {}\n", encoding="utf-8")
    imported_inputs.write_text(
        json.dumps(
            {
                "AQUARIUM_HB_Workflow.fastq1": "/path/to/sample_1.fastq.gz",
                "AQUARIUM_HB_Workflow.fastq2": "/path/to/sample_2.fastq.gz",
                "AQUARIUM_HB_Workflow.reference_fasta": "/path/to/genome.fa",
                "AQUARIUM_HB_Workflow.reference_gtf": "/path/to/genes.gtf",
                "AQUARIUM_HB_Workflow.reference_fasta_sa": "/path/to/genome.fa.sa",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    imported_dockerfile.write_text("FROM imported\n", encoding="utf-8")

    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请完成 circRNA benchmark register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "AQUARIUM-HB",
                "family": "github2workspace",
                "validation_status": "partial",
                "summary": "circRNA workflow.",
                "canonical_text": "circRNA benchmark",
                "input_media_types": ["json", "fastq-gzip", "fasta", "gtf", "sa"],
                "output_media_types": ["report"],
                "tags": ["wdl-completed", "domain:circrna"],
                "workflow_path": str(imported_wdl),
                "inputs_json_path": str(imported_inputs),
                "dockerfile_path": str(imported_dockerfile),
                "runtime_image": "AQUARIUM-HB",
                "entry_workflow": "AquariumWorkflow",
                "inputs": [
                    {"name": fastq1.name, "path": str(fastq1), "media_type": "fastq-gzip"},
                    {"name": fastq2.name, "path": str(fastq2), "media_type": "fastq-gzip"},
                    {"name": fasta.name, "path": str(fasta), "media_type": "fasta"},
                    {"name": gtf.name, "path": str(gtf), "media_type": "gtf"},
                    {"name": sa.name, "path": str(sa), "media_type": "sa"},
                ],
                "outputs": [],
                "expected_outputs": [],
                "score": 50,
                "rank": 0,
            }
        ],
    )

    result = await _invoke_worker_agent(
        agent=AsyncMock(),
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    staged_inputs = json.loads(
        (run_dir / "cases" / "AQUARIUM-HB" / "wdl" / "inputs.json").read_text(encoding="utf-8")
    )
    assert staged_inputs["AQUARIUM_HB_Workflow.fastq1"] == str(fastq1)
    assert staged_inputs["AQUARIUM_HB_Workflow.fastq2"] == str(fastq2)
    assert staged_inputs["AQUARIUM_HB_Workflow.reference_fasta"] == str(fasta)
    assert staged_inputs["AQUARIUM_HB_Workflow.reference_gtf"] == str(gtf)
    assert staged_inputs["AQUARIUM_HB_Workflow.reference_fasta_sa"] == str(sa)


@pytest.mark.asyncio
async def test_benchmark_register_falls_back_when_agentic_selection_output_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    (workspace_root / "operator_store").mkdir(parents=True)
    run_dir = workspace_root / "orchestration_runs" / "run-agentic-fallback"
    run_dir.mkdir(parents=True)
    benchmark_root = tmp_path / "benchmark" / "immune-escape"
    benchmark_root.mkdir(parents=True)
    node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "请在 immune-escape-covabdab-structural-bundle 数据集里选择适合做 protein language model scoring 的算子并完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": [],
            "excluded_tools": [],
            "benchmark_root": str(benchmark_root),
        },
    )
    monkeypatch.setattr(
        supervisor_runtime,
        "_collect_benchmark_operator_candidates",
        lambda **_kwargs: [
            {
                "name": "AutoDock-Vina",
                "family": "github2workspace",
                "validation_status": "completed",
                "summary": "Immune escape docking workflow for receptor ligand structural bundle.",
                "canonical_text": "vina docking receptor ligand pdbqt",
                "input_media_types": ["pdbqt"],
                "output_media_types": ["pdbqt"],
                "tags": ["wdl-completed", "domain:immune-escape"],
                "workflow_path": str(tmp_path / "autodock.wdl"),
                "inputs_json_path": str(tmp_path / "autodock.inputs.json"),
                "dockerfile_path": str(tmp_path / "AutoDock-Vina.Dockerfile"),
                "runtime_image": "AutoDock-Vina",
                "entry_workflow": "AutoDockVinaWorkflow",
                "inputs": [],
                "outputs": [],
                "expected_outputs": [],
                "score": 88,
                "rank": 0,
            },
            {
                "name": "esm",
                "family": "benchmark",
                "validation_status": "completed",
                "summary": "Protein language model scoring workflow for immune escape sequence variants.",
                "canonical_text": "protein language model fasta scoring",
                "input_media_types": ["fasta"],
                "output_media_types": ["json"],
                "tags": ["execution-ready", "domain:immune-escape"],
                "workflow_path": str(tmp_path / "esm.wdl"),
                "inputs_json_path": str(tmp_path / "esm.inputs.json"),
                "dockerfile_path": str(tmp_path / "esm.Dockerfile"),
                "runtime_image": "benchmark/esm:escape_bench",
                "entry_workflow": "ESMWorkflow",
                "inputs": [],
                "outputs": [],
                "expected_outputs": [],
                "score": 72,
                "rank": 1,
            },
        ],
    )
    (tmp_path / "autodock.wdl").write_text("workflow AutoDockVinaWorkflow {}", encoding="utf-8")
    (tmp_path / "autodock.inputs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "AutoDock-Vina.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "esm.wdl").write_text("workflow ESMWorkflow {}", encoding="utf-8")
    (tmp_path / "esm.inputs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "esm.Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    agent = AsyncMock()
    agent.ainvoke.return_value = {"messages": [AIMessage(content="not-json")]}
    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    assert agent.ainvoke.await_count == 1
    selection_report = json.loads((run_dir / "operator_selection.json").read_text(encoding="utf-8"))
    assert selection_report["selection_strategy"] == "operator_store_search"
    assert selection_report["selected_tools"] == ["AutoDock-Vina"]


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_expands_benchmark_after_register_round(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260506093000"
    workspace.mkdir(parents=True)

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "register":
            return WorkerResult(
                status="completed",
                summary="register ok",
                spawned_subgraph={"selected_tools": ["canu", "Flye"]},
            )
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await run_supervisor_orchestration(
        task="我想评估 /tmp/benchmark 里的 long-read-ecoli-pacbio benchmark 数据集在不同组装工具上的表现。",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    graph_1_payload = json.loads((result.run_dir / "graph_round_1.json").read_text())
    graph_2_payload = json.loads((result.run_dir / "graph_round_2.json").read_text())

    assert [node["node_id"] for node in graph_1_payload["nodes"]] == ["register"]
    assert [node["node_id"] for node in graph_2_payload["nodes"]] == [
        "canu",
        "Flye",
        "summarize",
    ]


@pytest.mark.asyncio
async def test_run_supervisor_orchestration_expands_benchmark_after_partial_register_ready_tools(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace" / "20260514164000"
    workspace.mkdir(parents=True)

    async def worker_runner(node: TaskNode) -> WorkerResult:
        if node.node_id == "register":
            return WorkerResult(
                status="partial",
                summary="register partially ready",
                failure_reason="execution_ready_incomplete",
                spawned_subgraph={
                    "selected_tools": ["ACValidator", "AutoCirc"],
                    "registered_tools": ["ACValidator", "AutoCirc", "AQUARIUM-HB"],
                    "blocked_tools": ["AQUARIUM-HB"],
                },
            )
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    result = await run_supervisor_orchestration(
        task="我想评估 /tmp/benchmark/circrna 里的 circRNA benchmark 数据集在不同工具上的表现。",
        workspace_root=workspace,
        worker_runner=worker_runner,
    )

    graph_2_payload = json.loads((result.run_dir / "graph_round_2.json").read_text())

    assert [node["node_id"] for node in graph_2_payload["nodes"]] == [
        "ACValidator",
        "AutoCirc",
        "summarize",
    ]


@pytest.mark.asyncio
async def test_invoke_worker_agent_falls_back_to_wdl_when_repo_native_command_is_missing(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-wdl"
    case_dir = run_dir / "cases" / "circompara2"
    (case_dir / "run").mkdir(parents=True, exist_ok=True)
    (case_dir / "wdl").mkdir(parents=True, exist_ok=True)
    (case_dir / "wdl" / "workflow.wdl").write_text("workflow CirComPara2Workflow {}", encoding="utf-8")
    (case_dir / "wdl" / "inputs.json").write_text("{}", encoding="utf-8")
    (case_dir / "analysis.json").write_text(
        json.dumps({"family": "unknown", "artifact_paths": [], "artifact_checksums": {}, "metrics": {}}),
        encoding="utf-8",
    )
    (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo_name": "circompara2",
                "family": "unknown",
                "dataset_key": "circrna-hela-rnaser-paired",
                "metric_keys": [],
                "phase_status": {"analysis": "pending", "summary": "pending"},
                "repo_native_entry": "",
                "repo_native_command_candidates": [],
            }
        ),
        encoding="utf-8",
    )
    run_dir.joinpath("manifest.json").write_text(json.dumps({"case_order": ["circompara2"]}), encoding="utf-8")

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase != "run-wdl:circompara2":
            raise AssertionError(f"unexpected phase: {phase}")
        output_file = case_dir / "wdl" / "circompara2.out"
        output_file.write_text("ok\n", encoding="utf-8")
        (case_dir / "wdl" / "status.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "returncode": 0,
                    "started_at": "2026-05-15T00:00:00Z",
                    "finished_at": "2026-05-15T00:00:01Z",
                    "elapsed_seconds": 1.0,
                    "log_path": str(case_dir / "wdl" / "miniwdl_run.log"),
                    "outputs_path": str(case_dir / "wdl" / "outputs.json"),
                    "output_artifacts": [str(output_file)],
                }
            ),
            encoding="utf-8",
        )
        (case_dir / "wdl" / "outputs.json").write_text(
            json.dumps({"outputs": {"CirComPara2Workflow.output": str(output_file)}}),
            encoding="utf-8",
        )
        return {"phase": phase, "command": command, "stdout": {"repo": "circompara2"}}

    node = TaskNode(
        node_id="circompara2",
        title="Run circompara2",
        objective="Execute the staged benchmark workload for circompara2 and record outputs, logs, and failure reasons.",
        capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "运行 circompara2 benchmark。",
            "run_dir": str(run_dir),
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("deterministic worker should bypass the model")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper):
        result = await _invoke_worker_agent(agent=agent, node=node, workspace_root=workspace_root)

    assert result.status == "completed"
    assert (case_dir / "run" / "status.json").exists()
    run_status = json.loads((case_dir / "run" / "status.json").read_text(encoding="utf-8"))
    assert run_status["execution_mode"] == "wdl_only"
    assert run_status["success"] is True


@pytest.mark.asyncio
async def test_invoke_worker_agent_uses_deterministic_benchmark_repo_helper(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-2"
    run_dir.mkdir(parents=True)
    register_node = TaskNode(
        node_id="register",
        title="Register benchmark cases",
        objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
        capability_bundles=["plan", "task_manage", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "在本地 benchmark 目录里只选择 spades 和 megahit，先完成 register。",
            "run_dir": str(run_dir),
            "selected_tools": ["spades", "megahit"],
        },
    )
    def fake_register_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "resolve-datasets":
            (run_dir / "dataset_resolution.json").write_text("{}", encoding="utf-8")
            (run_dir / "dataset_resolution.md").write_text("# datasets\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {}}
        if phase == "init":
            (run_dir / "benchmark_plan.json").write_text("{}", encoding="utf-8")
            (run_dir / "benchmark_plan.md").write_text("# plan\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"case_order": ["spades", "megahit"]}}
        repo = phase.split(":", 1)[1]
        case_dir = run_dir / "cases" / repo
        case_dir.mkdir(parents=True, exist_ok=True)
        if phase.startswith("prepare-case:"):
            (case_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "dataset_key": "short-read-ecoli-srr001666",
                        "metric_keys": ["contig_count", "assembly_size", "n50"],
                        "expected_outputs": ["final.contigs.fa", "log"],
                        "selected_input_files": {"reads_1": "/tmp/r1", "reads_2": "/tmp/r2"},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "dataset_selection.json").write_text("{}", encoding="utf-8")
            (case_dir / "dataset_manifest.json").write_text("{}", encoding="utf-8")
            (case_dir / "agent_task.md").write_text("# task\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": repo}}
        if phase.startswith("execution-ready:"):
            (case_dir / "execution_ready.json").write_text(
                json.dumps(
                    {
                        "ready": True,
                        "runtime_image": f"benchmark/{repo}",
                        "wdl_path": f"/tmp/{repo}.wdl",
                        "inputs_json_path": f"/tmp/{repo}.json",
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": repo}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_register_helper):
        await _invoke_worker_agent(
            agent=AsyncMock(),
            node=register_node,
            workspace_root=workspace_root,
        )

    node = TaskNode(
        node_id="megahit",
        title="Run megahit",
        objective="Execute the staged benchmark workload for megahit and record outputs, logs, and failure reasons.",
        capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "运行 megahit benchmark。",
            "run_dir": str(run_dir),
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("benchmark repo helper path should bypass the model")

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        case_dir = run_dir / "cases" / "megahit"
        output_dir = case_dir / "run" / "repo_native_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        if phase == "run-repo-native:megahit":
            (case_dir / "run" / "repo_native.log").write_text(
                "ALL DONE\n",
                encoding="utf-8",
            )
            (output_dir / "final.contigs.fa").write_text(">c1\nAAAA\n", encoding="utf-8")
            (output_dir / "log").write_text("done\n", encoding="utf-8")
            (case_dir / "run" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "elapsed_seconds": 1.5,
                        "command": command,
                        "log_path": str(case_dir / "run" / "repo_native.log"),
                        "output_dir": str(output_dir),
                        "output_artifacts": [
                            str(output_dir / "final.contigs.fa"),
                            str(output_dir / "log"),
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "megahit"}}
        if phase == "run-wdl:megahit":
            wdl_out = case_dir / "wdl" / "megahit.out"
            wdl_out.parent.mkdir(parents=True, exist_ok=True)
            wdl_out.write_text("ok\n", encoding="utf-8")
            (case_dir / "wdl" / "outputs.json").write_text(
                json.dumps({"outputs": {"MegahitAssembly.output": str(wdl_out)}}),
                encoding="utf-8",
            )
            (case_dir / "wdl" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "elapsed_seconds": 1.0,
                        "started_at": "2026-05-15T00:00:00Z",
                        "finished_at": "2026-05-15T00:00:01Z",
                        "log_path": str(case_dir / "wdl" / "miniwdl_run.log"),
                        "outputs_path": str(case_dir / "wdl" / "outputs.json"),
                        "output_artifacts": [str(wdl_out)],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "megahit"}}
        if phase == "analyze-case:megahit":
            (case_dir / "analysis.json").write_text(
                json.dumps(
                    {
                        "family": "short-read-assembly",
                        "artifact_paths": [
                            str(output_dir / "final.contigs.fa"),
                            str(output_dir / "log"),
                        ],
                        "artifact_checksums": {},
                        "metrics": {
                            "contig_count": 1,
                            "assembly_size": 4,
                            "n50": 4,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": "megahit"}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper):
        result = await _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "completed"
    assert "megahit" in result.summary
    assert (run_dir / "cases" / "megahit" / "run" / "result_manifest.json").exists()


@pytest.mark.asyncio
async def test_deterministic_benchmark_repo_helper_marks_missing_expected_outputs_partial(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-partial"
    case_dir = run_dir / "cases" / "canu"
    (case_dir / "run" / "repo_native_output").mkdir(parents=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_key": "long-read-canu-pacbio",
                "family": "long-read-assembly",
                "metric_keys": ["contig_count", "assembly_size", "n50"],
                "expected_outputs": ["assembly.fasta"],
                "phase_status": {},
                "repo_native_entry": "canu -correct -p ecoli -d out genomeSize=4.8m -pacbio <reads>",
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "execution_ready.json").write_text("{}", encoding="utf-8")
    (case_dir / "dataset_manifest.json").write_text("{}", encoding="utf-8")
    (case_dir / "run" / "repo_native.log").write_text("stopped after intermediate stage\n", encoding="utf-8")

    node = TaskNode(
        node_id="canu",
        title="Run canu",
        objective="Execute the staged benchmark workload for canu and record outputs, logs, and failure reasons.",
        capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "运行 canu benchmark。",
            "run_dir": str(run_dir),
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("benchmark repo helper path should bypass the model")

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "run-repo-native:canu":
            (case_dir / "run" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "elapsed_seconds": 1.5,
                        "command": command,
                        "log_path": str(case_dir / "run" / "repo_native.log"),
                        "output_dir": str(case_dir / "run" / "repo_native_output"),
                        "output_artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "canu"}}
        if phase == "run-wdl:canu":
            (case_dir / "wdl").mkdir(parents=True, exist_ok=True)
            (case_dir / "wdl" / "canu.out").write_text("ok\n", encoding="utf-8")
            (case_dir / "wdl" / "outputs.json").write_text(
                json.dumps({"outputs": {"canu_workflow.output": str(case_dir / "wdl" / "canu.out")}}),
                encoding="utf-8",
            )
            (case_dir / "wdl" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "elapsed_seconds": 1.0,
                        "started_at": "2026-05-15T00:00:00Z",
                        "finished_at": "2026-05-15T00:00:01Z",
                        "log_path": str(case_dir / "wdl" / "miniwdl_run.log"),
                        "outputs_path": str(case_dir / "wdl" / "outputs.json"),
                        "output_artifacts": [str(case_dir / "wdl" / "canu.out")],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "canu"}}
        if phase == "analyze-case:canu":
            (case_dir / "analysis.json").write_text(
                json.dumps(
                    {
                        "family": "long-read-assembly",
                        "artifact_paths": [],
                        "artifact_checksums": {},
                        "metrics": {},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": "canu"}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper):
        result = await _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "partial"
    assert result.failure_reason == "expected_outputs_missing"
    assert "Expected benchmark output files were not found" in result.summary


@pytest.mark.asyncio
async def test_retry_benchmark_case_runs_agentic_repair_before_deterministic_retry(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-retry-repair"
    case_dir = run_dir / "cases" / "canu"
    staged_wdl_dir = case_dir / "wdl"
    workflow_dir = staged_wdl_dir / "20260517_000000_CanuWorkflow"
    call_dir = workflow_dir / "call-CanuAssembly"
    call_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "run").mkdir(parents=True, exist_ok=True)
    staged_wdl = staged_wdl_dir / "canu.wdl"
    staged_inputs = staged_wdl_dir / "inputs.json"
    staged_wdl.write_text("workflow CanuWorkflow {}", encoding="utf-8")
    staged_inputs.write_text("{}", encoding="utf-8")
    (call_dir / "stderr.txt").write_text(
        "mkdir: cannot create directory '/output': Permission denied\n",
        encoding="utf-8",
    )
    (call_dir / "stdout.txt").write_text("canu starting\n", encoding="utf-8")
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo_name": "canu",
                "dataset_key": "long-read-canu-pacbio",
                "family": "long-read-assembly",
                "metric_keys": ["contig_count"],
                "expected_outputs": [],
                "phase_status": {"register": "completed"},
                "repo_native_entry": "",
                "repo_native_command_candidates": [],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "execution_ready.json").write_text(
        json.dumps(
            {
                "ready": True,
                "runtime_image": "benchmark/canu",
                "wdl_path": str(staged_wdl),
                "inputs_json_path": str(staged_inputs),
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "run" / "status.json").write_text(
        json.dumps({"success": False, "failure_reason": "wdl_failed"}),
        encoding="utf-8",
    )
    (case_dir / "wdl" / "status.json").write_text(
        json.dumps({"success": False, "returncode": 1, "failure_reason": "miniwdl_failed"}),
        encoding="utf-8",
    )
    node = TaskNode(
        node_id="retry_canu",
        title="Retry canu",
        objective="Retry the staged canu benchmark workflow.",
        capability_bundles=["wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "重试 canu benchmark。",
            "run_dir": str(run_dir),
        },
    )
    agent = AsyncMock()
    agent.ainvoke.return_value = {
        "messages": [
            AIMessage(
                content=json.dumps(
                    {
                        "repaired": True,
                        "modified_files": [str(staged_wdl)],
                        "summary": "patched the staged WDL to avoid writing to /output",
                    }
                )
            )
        ]
    }

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "run-wdl:canu":
            output_file = case_dir / "wdl" / "assembly.fasta"
            output_file.write_text(">contig\nACGT\n", encoding="utf-8")
            (case_dir / "wdl" / "outputs.json").write_text(
                json.dumps({"outputs": {"CanuWorkflow.assembly": str(output_file)}}),
                encoding="utf-8",
            )
            (case_dir / "wdl" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "started_at": "2026-05-17T00:00:00Z",
                        "finished_at": "2026-05-17T00:00:02Z",
                        "elapsed_seconds": 2.0,
                        "log_path": str(case_dir / "wdl" / "miniwdl_run.log"),
                        "outputs_path": str(case_dir / "wdl" / "outputs.json"),
                        "output_artifacts": [str(output_file)],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "canu"}}
        if phase == "analyze-case:canu":
            (case_dir / "analysis.json").write_text(
                json.dumps(
                    {
                        "family": "long-read-assembly",
                        "artifact_paths": [str(case_dir / "wdl" / "run_outputs" / "assembly.fasta")],
                        "artifact_checksums": {},
                        "metrics": {"contig_count": 1},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": "canu"}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper):
        result = await _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "completed"
    assert agent.ainvoke.await_count == 1
    repair_report = json.loads((case_dir / "repair_report.json").read_text(encoding="utf-8"))
    assert repair_report["repaired"] is True
    assert repair_report["modified_files"] == [str(staged_wdl)]
    prompt = agent.ainvoke.await_args.args[0]["messages"][0].content
    assert "Permission denied" in prompt
    assert str(staged_wdl) in prompt


@pytest.mark.asyncio
async def test_retry_benchmark_case_ignores_invalid_repair_output(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-retry-repair-invalid"
    case_dir = run_dir / "cases" / "megahit"
    staged_wdl_dir = case_dir / "wdl"
    staged_wdl_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "run").mkdir(parents=True, exist_ok=True)
    staged_wdl = staged_wdl_dir / "megahit.wdl"
    staged_inputs = staged_wdl_dir / "inputs.json"
    staged_wdl.write_text("workflow MegahitWorkflow {}", encoding="utf-8")
    staged_inputs.write_text("{}", encoding="utf-8")
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo_name": "megahit",
                "dataset_key": "short-read-ecoli-srr001666",
                "family": "short-read-assembly",
                "metric_keys": ["contig_count"],
                "expected_outputs": [],
                "phase_status": {"register": "completed"},
                "repo_native_entry": "",
                "repo_native_command_candidates": [],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "execution_ready.json").write_text(
        json.dumps(
            {
                "ready": True,
                "runtime_image": "benchmark/megahit",
                "wdl_path": str(staged_wdl),
                "inputs_json_path": str(staged_inputs),
            }
        ),
        encoding="utf-8",
    )
    node = TaskNode(
        node_id="retry_megahit",
        title="Retry megahit",
        objective="Retry the staged megahit benchmark workflow.",
        capability_bundles=["wdl_run", "metric_compute"],
        metadata={
            "task_type": "benchmark",
            "task": "重试 megahit benchmark。",
            "run_dir": str(run_dir),
        },
    )
    agent = AsyncMock()
    agent.ainvoke.return_value = {"messages": [AIMessage(content="not-json")]}

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase == "run-wdl:megahit":
            output_file = case_dir / "wdl" / "final.contigs.fa"
            output_file.write_text(">c1\nAAAA\n", encoding="utf-8")
            (case_dir / "wdl" / "outputs.json").write_text(
                json.dumps({"outputs": {"MegahitWorkflow.contigs": str(output_file)}}),
                encoding="utf-8",
            )
            (case_dir / "wdl" / "status.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "returncode": 0,
                        "started_at": "2026-05-17T00:00:00Z",
                        "finished_at": "2026-05-17T00:00:01Z",
                        "elapsed_seconds": 1.0,
                        "log_path": str(case_dir / "wdl" / "miniwdl_run.log"),
                        "outputs_path": str(case_dir / "wdl" / "outputs.json"),
                        "output_artifacts": [str(output_file)],
                    }
                ),
                encoding="utf-8",
            )
            return {"phase": phase, "command": command, "stdout": {"repo": "megahit"}}
        if phase == "analyze-case:megahit":
            (case_dir / "analysis.json").write_text(
                json.dumps(
                    {
                        "family": "short-read-assembly",
                        "artifact_paths": [str(case_dir / "wdl" / "run_outputs" / "final.contigs.fa")],
                        "artifact_checksums": {},
                        "metrics": {"contig_count": 1},
                    }
                ),
                encoding="utf-8",
            )
            (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
            return {"phase": phase, "command": command, "stdout": {"repo": "megahit"}}
        raise AssertionError(f"unexpected phase: {phase}")

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper):
        result = await _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "completed"
    assert agent.ainvoke.await_count == 1
    assert not (case_dir / "repair_report.json").exists()


@pytest.mark.asyncio
async def test_supervisor_worker_runner_triggers_benchmark_case_repair_on_retry(
    tmp_path: Path,
) -> None:
    node = TaskNode(
        node_id="retry_canu",
        title="Retry canu",
        objective="Retry the staged canu benchmark workflow.",
        capability_bundles=["wdl_run"],
        metadata={
            "task_type": "benchmark",
            "task": "重试 canu benchmark。",
            "run_dir": str(tmp_path / "workspace" / "orchestration_runs" / "run"),
        },
    )
    deterministic_result = WorkerResult(status="completed", summary="retry ok")
    agent = AsyncMock()
    with (
        patch.object(supervisor_runtime, "_maybe_prepare_worker_inputs", return_value=None),
        patch.object(supervisor_runtime, "_maybe_run_agentic_benchmark_register", AsyncMock(return_value=None)),
        patch.object(supervisor_runtime, "_maybe_run_agentic_benchmark_case_repair", AsyncMock(return_value={"repaired": True})) as repair_mock,
        patch.object(supervisor_runtime, "_maybe_run_deterministic_worker", return_value=deterministic_result),
    ):
        runner = SupervisorWorkerRunner(
            base_agent=agent,
            workspace_root=tmp_path / "workspace",
        )
        result = await runner.run(node)

    assert result is deterministic_result
    repair_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_deterministic_benchmark_workers_run_in_parallel_ready_batch(
    tmp_path: Path,
) -> None:
    graph = TaskGraph(
        graph_id="benchmark-r1",
        task_type="benchmark",
        round_index=1,
        nodes=[
            TaskNode(
                node_id="spades",
                title="Run spades",
                objective="run spades",
                capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
                metadata={"task_type": "benchmark"},
            ),
            TaskNode(
                node_id="megahit",
                title="Run megahit",
                objective="run megahit",
                capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
                metadata={"task_type": "benchmark"},
            ),
        ],
        edges=[],
    )
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_deterministic_worker(*, node: TaskNode, workspace_root: Path) -> WorkerResult | None:
        nonlocal active, max_active
        if node.node_id not in {"spades", "megahit"}:
            return None
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return WorkerResult(status="completed", summary=f"{node.node_id} ok")

    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("deterministic worker should bypass the model")

    with patch(
        "code2workspace_cli.supervisor_runtime._maybe_run_deterministic_worker",
        side_effect=fake_deterministic_worker,
    ):
        result = await execute_graph_round(
            graph,
            lambda node: _invoke_worker_agent(
                agent=agent,
                node=node,
                workspace_root=tmp_path,
            ),
        )

    assert result.completed_count == 2
    assert max_active == 2


@pytest.mark.asyncio
async def test_invoke_worker_agent_uses_deterministic_benchmark_summary_helper(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-3"
    case_dir = run_dir / "cases" / "megahit"
    case_dir.mkdir(parents=True)
    (case_dir / "run").mkdir()
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo_name": "megahit",
                "family": "short-read-assembly",
                "dataset_key": "short-read-ecoli-srr001666",
                "metric_keys": ["contig_count", "n50", "assembly_size"],
                "phase_status": {"analysis": "pending", "summary": "pending"},
                "expected_outputs": ["final.contigs.fa", "log"],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "run" / "status.json").write_text(
        json.dumps(
            {
                "success": True,
                "returncode": 0,
                "elapsed_seconds": 1.0,
                "output_artifacts": [
                    str(case_dir / "run" / "repo_native_output" / "final.contigs.fa"),
                    str(case_dir / "run" / "repo_native_output" / "log"),
                ],
            }
        ),
        encoding="utf-8",
    )
    output_dir = case_dir / "run" / "repo_native_output"
    output_dir.mkdir()
    (output_dir / "final.contigs.fa").write_text(">c1\nAAAA\n", encoding="utf-8")
    (output_dir / "log").write_text("done\n", encoding="utf-8")
    node = TaskNode(
        node_id="summarize",
        title="Summarize benchmark outcomes",
        objective="Aggregate tool results, metrics, blockers, and output paths into a benchmark summary.",
        capability_bundles=["metric_compute", "summarize"],
        metadata={
            "task_type": "benchmark",
            "task": "汇总 benchmark 结果。",
            "run_dir": str(run_dir),
            "selected_tools": ["megahit"],
        },
    )
    agent = AsyncMock()
    agent.ainvoke.side_effect = AssertionError("benchmark summarize helper path should bypass the model")

    def fake_helper(command: list[str], *, cwd: Path, phase: str) -> dict[str, object]:
        if phase != "analyze-case:megahit":
            raise AssertionError(f"unexpected phase: {phase}")
        (case_dir / "analysis.json").write_text(
            json.dumps(
                {
                    "family": "short-read-assembly",
                    "artifact_paths": [
                        str(output_dir / "final.contigs.fa"),
                        str(output_dir / "log"),
                    ],
                    "artifact_checksums": {},
                    "metrics": {
                        "contig_count": 1,
                        "assembly_size": 4,
                        "n50": 4,
                    },
                }
            ),
            encoding="utf-8",
        )
        (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")
        return {"phase": phase, "command": command, "stdout": {"repo": "megahit"}}

    with patch("code2workspace_cli.supervisor_runtime._run_helper_json_command", side_effect=fake_helper):
        result = await _invoke_worker_agent(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )

    assert result.status == "completed"
    assert (run_dir / "benchmark_supervisor_summary.json").exists()
    assert (run_dir / "benchmark_supervisor_summary.md").exists()


@pytest.mark.asyncio
async def test_benchmark_final_response_uses_worker_agent_not_case_helper(
    tmp_path: Path,
) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "orchestration_runs" / "run-final"
    run_dir.mkdir(parents=True)
    node = TaskNode(
        node_id="final_response",
        title="Write final user response",
        objective="Turn benchmark results into the final user-facing answer.",
        capability_bundles=["summarize", "validate"],
        metadata={
            "task_type": "benchmark",
            "task": "汇总 benchmark 结果。",
            "run_dir": str(run_dir),
            "selected_tools": ["spades", "megahit"],
        },
    )
    agent = AsyncMock()
    agent.ainvoke.return_value = {
        "messages": [
            AIMessage(
                content=json.dumps(
                    {
                        "status": "completed",
                        "summary": "spades 和 megahit 均已完成，spades 在 N50 上更优。",
                    },
                    ensure_ascii=False,
                )
            )
        ]
    }

    result = await _invoke_worker_agent(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    assert result.summary == "spades 和 megahit 均已完成，spades 在 N50 上更优。"
    assert agent.ainvoke.await_count == 1
