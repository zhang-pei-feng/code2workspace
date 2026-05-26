"""Supervisor-enabled orchestration runtime for CLI long tasks."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from langchain.agents import AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import Checkpointer, Command, interrupt

from code2workspace.orchestration_runtime import (
    CaseIndexEntry,
    CaseTraceRecord,
    GenericApproach,
    HeuristicSupervisorPlanner,
    ModelRefusalError,
    SupervisorDecision,
    TaskClassification,
    TaskNode,
    WorkerResult,
    _extract_model_refusal_message,
    _extract_benchmark_excluded_tools,
    _task_requests_multiple_benchmark_tools,
    classify_task,
    classify_task_with_model,
    decide_supervisor_step,
    execute_graph_round,
)
from code2workspace_cli._env_vars import get_env
from code2workspace_cli.benchmark_result_store import (
    BENCHMARK_RECORD_NAME,
    BenchmarkResultSearchFilter,
    BenchmarkResultStore,
)
from code2workspace_cli.dataset_store import DatasetSearchFilter, DatasetStore
from code2workspace_cli.operator_store import (
    OperatorSearchFilter,
    OperatorStore,
    build_benchmark_operator_manifest,
    build_github2workspace_operator_manifest,
)
from code2workspace_cli.supervisor_evaluation import write_evaluation_for_run
from code2workspace_cli.supervisor_capabilities import (
    describe_capabilities,
    family_guidance_lines,
    generic_experience_guidance_lines,
    node_guidance_lines,
)

logger = logging.getLogger(__name__)

SUPERVISOR_REPORT_NODE_TIMEOUT_SECONDS = 20 * 60
"""Default timeout for report-family supervisor worker nodes, in seconds."""

SUPERVISOR_REPORT_NODE_TIMEOUT_ENV = (
    "EPIMINDAGENT_SUPERVISOR_REPORT_NODE_TIMEOUT_SECONDS"
)
SUPERVISOR_WORKER_HEARTBEAT_SECONDS = 15.0
"""Default heartbeat interval for long-running supervisor worker nodes, in seconds."""

SUPERVISOR_WORKER_HEARTBEAT_ENV = "EPIMINDAGENT_SUPERVISOR_WORKER_HEARTBEAT_SECONDS"
SUPERVISOR_RAW_WORKER_TRACE_ENV = "EPIMINDAGENT_SUPERVISOR_RAW_WORKER_TRACE"
"""Set to 0/false/no/off to skip verbose per-worker raw trace artifacts."""

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from langgraph.pregel import Pregel


@dataclass(slots=True)
class SupervisorRunResult:
    run_dir: Path
    final_summary: str
    user_response: str
    final_decision: SupervisorDecision
    round_count: int


@dataclass(frozen=True, slots=True)
class GenericApproachOption:
    approach: GenericApproach
    label: str
    summary: str
    execution_focus: str

    def to_dict(self) -> dict[str, str]:
        return {
            "approach": self.approach,
            "label": self.label,
            "summary": self.summary,
            "execution_focus": self.execution_focus,
        }


@dataclass(frozen=True, slots=True)
class SupervisorWorkerSubagent:
    """Runnable-backed worker selected directly by the supervisor runtime."""

    name: str
    runnable: Any
    node_ids: frozenset[str] = frozenset()

    def matches(self, node: TaskNode) -> bool:
        if node.node_id in self.node_ids:
            return True
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        report_lane_base = str(metadata.get("report_lane_base", "")).strip()
        if report_lane_base and report_lane_base in self.node_ids:
            return True
        return any(node.node_id.startswith(f"{node_id}_") for node_id in self.node_ids)


@dataclass(frozen=True, slots=True)
class GitHubRepoSpec:
    owner: str
    name: str
    clone_url: str


class SupervisorWorkerRunner:
    """Execute supervisor nodes through deterministic adapters or subagents."""

    def __init__(
        self,
        *,
        base_agent: Any,
        workspace_root: Path,
        default_subagent: Any | None = None,
        subagents: list[SupervisorWorkerSubagent] | None = None,
        register_selector: Any | None = None,
    ) -> None:
        self._base_agent = base_agent
        self._workspace_root = workspace_root
        self._default_subagent = default_subagent
        self._subagents = list(subagents or [])
        self._register_selector = register_selector

    async def run(self, node: TaskNode) -> WorkerResult:
        prepared = await asyncio.to_thread(
            _maybe_prepare_worker_inputs,
            node=node,
            workspace_root=self._workspace_root,
        )
        if prepared is not None:
            return prepared
        agentic = await _maybe_run_agentic_benchmark_register(
            agent=self._register_selector or self._select_runnable(node),
            node=node,
            workspace_root=self._workspace_root,
        )
        if agentic is not None:
            return agentic
        if _is_agent_owned_benchmark_case_node(node):
            return await _invoke_worker_runnable(
                agent=self._select_runnable(node),
                node=node,
                workspace_root=self._workspace_root,
            )
        await _maybe_run_agentic_benchmark_case_repair(
            agent=self._select_runnable(node),
            node=node,
            workspace_root=self._workspace_root,
        )
        deterministic = await asyncio.to_thread(
            _maybe_run_deterministic_worker,
            node=node,
            workspace_root=self._workspace_root,
        )
        if deterministic is not None:
            return deterministic
        return await _invoke_worker_runnable(
            agent=self._select_runnable(node),
            node=node,
            workspace_root=self._workspace_root,
        )

    def _select_runnable(self, node: TaskNode) -> Any:
        for subagent in self._subagents:
            if subagent.matches(node):
                return subagent.runnable
        return self._default_subagent or self._base_agent


_BENCHMARK_REGISTER_AGENTIC_SELECTION_ENV = (
    "EPIMINDAGENT_BENCHMARK_REGISTER_AGENTIC_SELECTION"
)
_DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION = "1"
_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_ENV = (
    "EPIMINDAGENT_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_SECONDS"
)
_DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_SECONDS = 45.0
_INTERNAL_BENCHMARK_REGISTER_SELECTOR_TAG = "internal_benchmark_register_selector"
_BENCHMARK_CASE_AGENTIC_REPAIR_ENV = "EPIMINDAGENT_BENCHMARK_CASE_AGENTIC_REPAIR"
_DEFAULT_BENCHMARK_CASE_AGENTIC_REPAIR = "1"
_BENCHMARK_REGISTER_AGENTIC_CANDIDATE_LIMIT = 12
_BENCHMARK_PREBUILD_TIMEOUT_SECONDS = 14400
_TASK_PATH_RE = re.compile(r"(/[^ \n\t,;:]+)")
_GITHUB_REPO_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:\.git)?(?:[/?#][^\s]*)?",
    re.IGNORECASE,
)
_GITHUB_SSH_URL_RE = re.compile(
    r"git@github\.com:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:\.git)?$",
    re.IGNORECASE,
)
_TRANSIENT_WORKER_ERROR_MARKERS = (
    "APIConnectionError",
    "InternalServerError",
    "RemoteProtocolError",
    "APIError",
    "upstream_error",
    "Upstream request failed",
    "Connection error",
    "Error code: 502",
    "Error code: 503",
    "Error code: 504",
)
_GENERIC_WORKER_TRANSIENT_RETRIES = 2
_WORKER_PROMPT_MODE_ENV = "EPIMINDAGENT_SUPERVISOR_WORKER_PROMPT_MODE"
_DEFAULT_WORKER_PROMPT_MODE = "messages"
_URL_RE = re.compile(r"https?://[^\s<>)\"']+")
_LOCAL_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w:])/(?:[^\s`'\"<>{}\[\]，。；：！？、]+)")
_GITHUB_REPO_MATERIALIZE_TIMEOUT_SECONDS = 1800
_LOCAL_REPO_SEARCH_MAX_DEPTH = 4
_INTERACTIVE_CONFIRMATION_FOOTER = "如果你觉得可以，我就开始执行任务。"
_INTERACTIVE_PROPOSAL_SYSTEM_PROMPT = f"""你是 EpiMindAgent 交互入口的方案确认助手。

当前阶段只负责澄清意图和整理执行方案，不执行任务。

规则：
- 不调用工具、不运行命令、不读取或修改文件，也不要声称已经检查过本地文件。
- 如果用户意图不清楚，先指出需要确认的信息，并给出一个可调整的初步方案。
- 如果用户正在修改需求，整合最近对话形成新的方案。
- 输出要简洁、直接，默认使用中文。
- 最后一行必须是：{_INTERACTIVE_CONFIRMATION_FOOTER}
"""
_CODE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3] / "code_repository"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SHARED_OPERATOR_STORE_ROOT_ENV = "EPIMINDAGENT_SHARED_OPERATOR_STORE_ROOT"
_SHARED_DATASET_STORE_ROOT_ENV = "EPIMINDAGENT_SHARED_DATASET_STORE_ROOT"
_BENCHMARK_COMPARISON_HISTORY_STORE_DIR = "benchmark_comparison_history_store"
_SHARED_BENCHMARK_COMPARISON_HISTORY_STORE_ROOT_ENV = (
    "EPIMINDAGENT_SHARED_BENCHMARK_COMPARISON_HISTORY_STORE_ROOT"
)
_BENCHMARK_HISTORY_BACKFILL_ATTEMPTED: set[Path] = set()


class SQLiteCaseIndex:
    """Rebuildable case index over canonical workspace artifacts."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    run_dir TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    searchable_text TEXT NOT NULL
                )
                """
            )

    def rebuild_from_workspace_root(self, workspace_root: Path) -> None:
        runs = _discover_run_dirs(workspace_root)
        with self._connect() as conn:
            conn.execute("DELETE FROM cases")
            for run_dir in runs:
                record = self._load_case_entry(run_dir)
                if record is None:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cases
                    (run_dir, task, task_type, summary, searchable_text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_dir,
                        record.task,
                        record.task_type,
                        record.summary,
                        f"{record.task}\n{record.summary}",
                    ),
                )

    def search(self, query: str, *, limit: int = 3) -> list[CaseTraceRecord]:
        query_tokens = _tokenize(query)
        rows: list[CaseIndexEntry] = []
        with self._connect() as conn:
            for row in conn.execute(
                "SELECT run_dir, task, task_type, summary, searchable_text FROM cases"
            ):
                run_dir, task, task_type, summary, searchable_text = row
                searchable = str(searchable_text)
                score = sum(token in searchable.casefold() for token in query_tokens)
                if score == 0:
                    continue
                rows.append(
                    CaseIndexEntry(
                        run_dir=str(run_dir),
                        task=str(task),
                        task_type=str(task_type),
                        summary=str(summary),
                        score=float(score),
                    )
                )
        rows.sort(key=lambda item: item.score, reverse=True)
        return [item.to_case_trace_record() for item in rows[:limit]]

    def _load_case_entry(self, run_dir: Path) -> CaseIndexEntry | None:
        request_path = run_dir / "request.json"
        decision_path = run_dir / "final_decision.json"
        summary_path = run_dir / "final_summary.md"
        if not (
            request_path.exists() and decision_path.exists() and summary_path.exists()
        ):
            return None
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
        return CaseIndexEntry(
            run_dir=str(run_dir),
            task=str(request_payload.get("task", "")),
            task_type=str(decision_payload.get("task_type", "generic")),
            summary=summary_path.read_text(encoding="utf-8"),
        )


async def run_supervisor_orchestration(
    *,
    task: str,
    workspace_root: Path,
    worker_runner,
    planner: HeuristicSupervisorPlanner | None = None,
    max_rounds: int = 2,
    classification: TaskClassification | None = None,
    classification_details: dict[str, Any] | None = None,
    generic_approach_selector: Callable[
        [list[GenericApproachOption], Path], Awaitable[GenericApproach]
    ]
    | None = None,
) -> SupervisorRunResult:
    planner = planner or HeuristicSupervisorPlanner()
    run_dir = _new_run_dir(workspace_root)

    case_root = _case_collection_root(workspace_root)
    index = SQLiteCaseIndex(case_root / "orchestration_case_index.sqlite3")
    index.rebuild_from_workspace_root(case_root)
    retrieved_cases = index.search(task, limit=3)

    _write_json(
        run_dir / "request.json", {"task": task, "workspace_root": str(workspace_root)}
    )
    _write_json(
        run_dir / "retrieved_cases.json",
        {"cases": [item.to_dict() for item in retrieved_cases]},
    )

    task_classification = classification or classify_task(task)
    task_type = task_classification.primary_type
    _write_json(
        run_dir / "task_classification.json",
        {
            "task": task,
            "task_type": task_type,
            "guidance_ids": list(task_classification.guidance_ids),
            "details": classification_details or {"source": "rules_fallback"},
        },
    )
    _emit_supervisor_event(
        kind="run_started",
        task=task,
        task_type=task_type,
        guidance_ids=list(task_classification.guidance_ids),
        classification_details=classification_details or {"source": "rules_fallback"},
        run_dir=str(run_dir),
        retrieved_case_count=len(retrieved_cases),
    )
    rounds = []
    selected_generic_approach: GenericApproach | None = None
    final_decision = SupervisorDecision(decision="stop", reason="No rounds executed.")
    effective_max_rounds = max_rounds
    if task_type == "benchmark":
        effective_max_rounds = max(max_rounds, 3)
    while True:
        graph = planner.plan_round(
            task=task,
            retrieved_cases=retrieved_cases,
            prior_rounds=rounds,
            generic_approach=selected_generic_approach,
            classification_override=task_classification,
        )
        _write_json(run_dir / f"graph_round_{graph.round_index}.json", graph.to_dict())
        _emit_supervisor_event(
            kind="round_started",
            round_index=graph.round_index,
            graph_id=graph.graph_id,
            task_type=graph.task_type,
            node_ids=[node.node_id for node in graph.nodes],
        )
        try:
            round_result = await execute_graph_round(
                graph,
                lambda node: _run_worker_and_capture(
                    node=node,
                    graph_round=graph.round_index,
                    run_dir=run_dir,
                    worker_runner=worker_runner,
                ),
            )
        except ModelRefusalError as exc:
            return _finalize_refusal_run(
                run_dir=run_dir,
                task=task,
                task_type=task_type,
                rounds=rounds,
                refusal=exc,
            )
        rounds.append(round_result)
        if task_type == "generic" and _generic_analysis_round_finished(round_result):
            _emit_supervisor_event(
                kind="generic_plan_created",
                run_dir=str(run_dir),
                has_spawned_subgraph=bool(
                    round_result.node_results[0].spawned_subgraph
                ),
            )
            continue
        if task_type == "report" and _report_init_round_finished(round_result):
            _emit_supervisor_event(
                kind="report_plan_created",
                run_dir=str(run_dir),
                has_spawned_subgraph=bool(
                    round_result.node_results[0].spawned_subgraph
                ),
            )
            continue
        if task_type == "benchmark" and _benchmark_register_round_finished(
            round_result
        ):
            _emit_supervisor_event(
                kind="benchmark_register_completed",
                round_index=round_result.graph.round_index,
                selected_tools=_benchmark_selected_tools_from_round_result(
                    round_result
                ),
            )
            continue
        final_decision = decide_supervisor_step(
            round_result, max_rounds=effective_max_rounds
        )
        if final_decision.decision == "replan":
            continue
        break

    final_summary = _render_final_summary(
        task=task,
        rounds=rounds,
        decision=final_decision,
        generic_approach=selected_generic_approach,
    )
    try:
        user_response = await _render_user_response(
            task=task,
            task_type=task_type,
            rounds=rounds,
            decision=final_decision,
            final_summary=final_summary,
            run_dir=run_dir,
            worker_runner=worker_runner,
        )
    except ModelRefusalError as exc:
        return _finalize_refusal_run(
            run_dir=run_dir,
            task=task,
            task_type=task_type,
            rounds=rounds,
            refusal=exc,
        )
    if task_type == "report":
        user_response = _normalize_report_markdown_syntax(user_response)
    user_response = _relativize_user_facing_paths(user_response, run_dir=run_dir)
    (run_dir / "final_summary.md").write_text(final_summary, encoding="utf-8")
    (run_dir / "final_response.md").write_text(user_response, encoding="utf-8")
    _write_json(
        run_dir / "final_decision.json",
        {
            "decision": final_decision.decision,
            "reason": final_decision.reason,
            "failed_nodes": final_decision.failed_nodes,
            "task_type": task_type,
            "generic_approach": selected_generic_approach,
            "round_count": len(rounds),
            "run_dir": str(run_dir),
            "final_response_path": str(run_dir / "final_response.md"),
        },
    )
    _write_supervisor_evaluation(run_dir)
    if task_type == "github2workspace":
        _materialize_github2workspace_operator_product(
            task=task,
            workspace_root=workspace_root,
            run_dir=run_dir,
            rounds=rounds,
            final_decision=final_decision,
        )
    _emit_supervisor_event(
        kind="run_finished",
        decision=final_decision.decision,
        reason=final_decision.reason,
        failed_nodes=list(final_decision.failed_nodes),
        generic_approach=selected_generic_approach,
        round_count=len(rounds),
        run_dir=str(run_dir),
    )
    index.rebuild_from_workspace_root(case_root)
    return SupervisorRunResult(
        run_dir=run_dir,
        final_summary=final_summary,
        user_response=user_response,
        final_decision=final_decision,
        round_count=len(rounds),
    )


def build_supervisor_enabled_agent(
    *,
    base_agent,
    fallback_agent=None,
    workspace_root: Path,
    worker_agent=None,
    worker_subagents: list[SupervisorWorkerSubagent] | None = None,
    classifier_model=None,
    enable_generic_ask_user: bool = True,
    interactive_confirmation_mode: bool = False,
    checkpointer: Checkpointer | None = None,
) -> Pregel:
    """Wrap the base agent with supervisor routing for supported task types."""
    fallback_agent = fallback_agent or base_agent

    async def route(state: AgentState) -> Command[str]:
        task = _latest_human_text(state)
        if _latest_human_route_mode(state) == "fallback":
            return Command(goto="fallback")
        if task:
            if interactive_confirmation_mode and not _latest_human_requests_execution(
                state
            ):
                return Command(goto="proposal")
            return Command(goto="supervise")
        return Command(goto="fallback")

    async def proposal(state: AgentState) -> dict[str, object]:
        text = await _render_interactive_execution_proposal(
            state=state,
            proposal_model=classifier_model,
        )
        return {"messages": [AIMessage(content=text)]}

    async def supervise(state: AgentState) -> dict[str, object]:
        task = (
            _confirmed_interactive_execution_task(state)
            if interactive_confirmation_mode
            else _latest_human_text(state)
        ) or ""
        try:
            (
                task_classification,
                classification_details,
            ) = await classify_task_with_model(
                model=classifier_model,
                task=task,
            )
        except ModelRefusalError as exc:
            return {"messages": [AIMessage(content=exc.user_message)]}
        worker_runner = SupervisorWorkerRunner(
            base_agent=base_agent,
            workspace_root=workspace_root,
            default_subagent=worker_agent,
            subagents=worker_subagents,
            register_selector=classifier_model,
        )
        result = await run_supervisor_orchestration(
            task=task,
            workspace_root=workspace_root,
            worker_runner=worker_runner.run,
            classification=task_classification,
            classification_details=classification_details,
            generic_approach_selector=(
                _select_generic_approach_with_user
                if enable_generic_ask_user and not interactive_confirmation_mode
                else None
            ),
        )
        return {"messages": [AIMessage(content=result.user_response)]}

    builder = StateGraph(AgentState)
    builder.add_node("route", route)
    builder.add_node("fallback", fallback_agent)
    builder.add_node("proposal", proposal)
    builder.add_node("supervise", supervise)
    builder.add_edge(START, "route")
    builder.add_edge("fallback", END)
    builder.add_edge("proposal", END)
    builder.add_edge("supervise", END)
    return builder.compile(checkpointer=checkpointer)


def _generic_analysis_round_finished(round_result: Any) -> bool:
    return (
        round_result.graph.task_type == "generic"
        and round_result.graph.round_index == 1
        and [item.node_id for item in round_result.node_results] == ["init_generic"]
        and len(getattr(round_result.graph, "nodes", []) or []) == 1
        and round_result.node_results[0].status == "completed"
    )


def _benchmark_register_round_finished(round_result: Any) -> bool:
    return (
        round_result.graph.task_type == "benchmark"
        and [item.node_id for item in round_result.node_results]
        in (["register"], ["retry_register"])
        and round_result.node_results[0].status in {"completed", "partial"}
        and bool(_benchmark_selected_tools_from_round_result(round_result))
    )


def _benchmark_selected_tools_from_round_result(round_result: Any) -> list[str]:
    if not round_result.node_results:
        return []
    payload = round_result.node_results[0].spawned_subgraph
    if not isinstance(payload, dict):
        return []
    selected_tools = payload.get("selected_tools")
    if not isinstance(selected_tools, list):
        return []
    return [
        str(item) for item in selected_tools if isinstance(item, str) and item.strip()
    ]


def _report_init_round_finished(round_result: Any) -> bool:
    return (
        round_result.graph.task_type == "report"
        and round_result.graph.round_index == 1
        and [item.node_id for item in round_result.node_results] == ["init_report"]
        and len(getattr(round_result.graph, "nodes", []) or []) == 1
        and round_result.node_results[0].status == "completed"
    )


def _benchmark_has_repo_native_command(case_manifest: dict[str, object]) -> bool:
    entry = str(case_manifest.get("repo_native_entry", "")).strip()
    if entry:
        return True
    candidates = case_manifest.get("repo_native_command_candidates", [])
    return isinstance(candidates, list) and any(
        isinstance(item, str) and item.strip() for item in candidates
    )


def _build_generic_approach_options(
    *,
    task: str,
    analysis_summary: str,
) -> list[GenericApproachOption]:
    task_hint = (
        task.strip().splitlines()[0][:120] if task.strip() else "the requested task"
    )
    analysis_hint = analysis_summary.strip()[:220] or "The analysis node completed."
    return [
        GenericApproachOption(
            approach="simple",
            label="简单",
            summary=f"只完成最小可用结果：围绕 `{task_hint}` 做一个低成本、低风险的第一版。",
            execution_focus=(
                "Use the analysis result to produce the smallest verified answer or artifact; "
                "skip optional checks and broad exploration."
            ),
        ),
        GenericApproachOption(
            approach="medium",
            label="中等",
            summary=f"完成主目标并做基础验证：基于分析结论 `{analysis_hint}` 走一条均衡执行路径。",
            execution_focus=(
                "Complete the main requested outcome with focused verification, concise artifacts, "
                "and a clear summary of tradeoffs."
            ),
        ),
        GenericApproachOption(
            approach="difficult",
            label="困难",
            summary="做更完整的版本：覆盖更多边界、验证和产物整理，但仍不越过原始需求边界。",
            execution_focus=(
                "Broaden implementation or investigation depth, include stronger verification, "
                "and preserve richer evidence for follow-up work."
            ),
        ),
    ]


def _write_generic_approach_options(
    *,
    run_dir: Path,
    options: list[GenericApproachOption],
) -> None:
    payload = {"options": [option.to_dict() for option in options]}
    _write_json(run_dir / "generic_approach_options.json", payload)
    lines = ["# Generic Approach Options", ""]
    for option in options:
        lines.extend(
            [
                f"## {option.label}",
                "",
                f"- approach: `{option.approach}`",
                f"- summary: {option.summary}",
                f"- execution_focus: {option.execution_focus}",
                "",
            ]
        )
    (run_dir / "generic_approach_options.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


async def _select_generic_approach_with_user(
    options: list[GenericApproachOption],
    run_dir: Path,
) -> GenericApproach:
    choices = [
        {"value": f"{option.label} ({option.approach}) - {option.summary}"}
        for option in options
    ]
    response = interrupt(
        {
            "type": "ask_user",
            "tool_call_id": f"generic-approach-{run_dir.name}",
            "questions": [
                {
                    "question": "请选择 generic 任务的执行复杂度。Supervisor 已完成任务分析，选择后再继续执行。",
                    "type": "multiple_choice",
                    "choices": choices,
                    "required": True,
                }
            ],
        }
    )
    return _parse_generic_approach_response(response, options)


def _parse_generic_approach_response(
    response: object,
    options: list[GenericApproachOption],
) -> GenericApproach:
    if not isinstance(response, dict):
        return "medium"
    answers = response.get("answers")
    if not isinstance(answers, list) or not answers:
        return "medium"
    answer = str(answers[0]).casefold()
    aliases: dict[GenericApproach, tuple[str, ...]] = {
        "simple": ("simple", "简单", "简易", "低", "轻量"),
        "medium": ("medium", "中等", "均衡", "普通"),
        "difficult": ("difficult", "困难", "复杂", "完整", "深入"),
    }
    for option in options:
        if any(alias in answer for alias in aliases[option.approach]):
            return option.approach
    return "medium"


def _generic_approach_label(
    approach: GenericApproach,
    options: list[GenericApproachOption],
) -> str:
    return next(
        (option.label for option in options if option.approach == approach),
        "中等",
    )


def _is_transient_worker_exception(exc: Exception) -> bool:
    rendered = f"{type(exc).__name__}: {exc}"
    return any(marker in rendered for marker in _TRANSIENT_WORKER_ERROR_MARKERS)


def _emit_supervisor_event(**payload: object) -> None:
    """Best-effort emit of supervisor runtime events into the graph stream."""
    try:
        stream_writer = get_stream_writer()
    except RuntimeError:
        return
    try:
        stream_writer({"supervisor_event": payload})
    except Exception:
        return


def _new_run_dir(workspace_root: Path) -> Path:
    """Create a unique orchestration run directory under the workspace root."""
    base = workspace_root / "orchestration_runs"
    while True:
        candidate = base / _run_id()
        try:
            (candidate / "node_traces").mkdir(parents=True, exist_ok=False)
            (candidate / "worker_outputs").mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return candidate


def _maybe_prepare_worker_inputs(
    *, node: TaskNode, workspace_root: Path
) -> WorkerResult | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if metadata.get("task_type") != "github2workspace":
        return None
    if node.node_id not in {"inspect", "retry_inspect"}:
        if node.node_id in {"wdl", "retry_wdl"}:
            return _reuse_github2workspace_successful_wdl_smoke(
                node=node,
                workspace_root=workspace_root,
            )
        return None
    return _prepare_github2workspace_repo(node=node, workspace_root=workspace_root)


def _reuse_github2workspace_successful_wdl_smoke(
    *,
    node: TaskNode,
    workspace_root: Path,
) -> WorkerResult | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    run_dir = _optional_path(metadata.get("run_dir"))
    if run_dir is None:
        return None
    smoke_root = run_dir / "wdl_smoke_run"
    if not smoke_root.exists():
        return None
    workflow_dirs = [
        path
        for path in smoke_root.iterdir()
        if path.is_dir() and (path / "outputs.json").exists()
    ]
    if not workflow_dirs:
        return None
    latest_workflow_dir = max(workflow_dirs, key=lambda path: path.stat().st_mtime)
    outputs_path = latest_workflow_dir / "outputs.json"
    workflow_log = latest_workflow_dir / "workflow.log"
    outputs_payload = _read_json_file(outputs_path)
    if not isinstance(outputs_payload, dict) or not outputs_payload:
        return None
    workflow_log_text = _read_text_excerpt(workflow_log, max_chars=12000)
    if "exit_code: 0" not in workflow_log_text:
        return None

    task = str(metadata.get("task", "")).strip()
    spec = _github_repo_spec_from_task(task)
    repo_dir = workspace_root / spec.name if spec is not None else workspace_root
    artifacts: list[str] = []
    if repo_dir.exists():
        for candidate in sorted(repo_dir.glob("*.wdl")):
            artifacts.append(str(candidate))
        for candidate in sorted(repo_dir.glob("*inputs*.json")):
            artifacts.append(str(candidate))
    for candidate in (outputs_path, workflow_log):
        if candidate.exists():
            artifacts.append(str(candidate))
    for value in outputs_payload.values():
        if isinstance(value, str) and Path(value).exists():
            artifacts.append(value)
    artifacts = sorted(dict.fromkeys(artifacts))

    repo_name = spec.name if spec is not None else "repository"
    return WorkerResult(
        status="partial",
        summary=(
            f"Found existing successful miniwdl smoke validation artifacts for {repo_name}, "
            "but the repository's main-function WDL path is not yet verified."
        ),
        artifacts=artifacts,
        evidence=[
            f"Existing miniwdl smoke outputs found at {outputs_path}.",
            f"Workflow log {workflow_log} records docker task exit_code: 0.",
            "Smoke validation alone is not sufficient evidence that the primary operator workflow ran successfully.",
        ],
        next_action_hint=(
            "Use the generated main-function WDL and real repository inputs if available; "
            "return completed only after the primary workflow writes non-empty outputs JSON and declared main outputs exist."
        ),
        failure_reason="main_wdl_not_yet_validated",
    )


def _prepare_github2workspace_repo(
    *, node: TaskNode, workspace_root: Path
) -> WorkerResult | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    task = str(metadata.get("task", "")).strip()
    spec = _github_repo_spec_from_task(task)
    if spec is None:
        return None

    destination = workspace_root / spec.name
    run_dir = _optional_path(metadata.get("run_dir"))
    log_path = (
        run_dir / "github_repo_materialization.json"
        if run_dir is not None
        else workspace_root / "github_repo_materialization.json"
    )
    if _looks_like_git_repo(destination):
        _write_github_repo_materialization_log(
            log_path,
            {
                "repo": spec.clone_url,
                "destination": str(destination),
                "selected_strategy": "existing_workspace_copy",
                "attempts": [
                    {
                        "strategy": "existing_workspace_copy",
                        "status": "success",
                        "detail": f"Using existing repository at {destination}",
                    }
                ],
            },
        )
        return None

    attempts: list[dict[str, str]] = []
    cached_repo = _find_cached_code_repository(spec)
    if cached_repo is not None:
        _remove_partial_repo(destination)
        try:
            shutil.copytree(cached_repo, destination, symlinks=True)
        except OSError as exc:
            attempts.append(
                {
                    "strategy": "code_repository_copy",
                    "status": "failed",
                    "detail": str(exc),
                }
            )
        else:
            if _looks_like_git_repo(destination):
                attempts.append(
                    {
                        "strategy": "code_repository_copy",
                        "status": "success",
                        "detail": f"Copied cached repository from {cached_repo}",
                    }
                )
                _write_github_repo_materialization_log(
                    log_path,
                    {
                        "repo": spec.clone_url,
                        "destination": str(destination),
                        "selected_strategy": "code_repository_copy",
                        "cached_repo": str(cached_repo),
                        "attempts": attempts,
                    },
                )
                return None
            attempts.append(
                {
                    "strategy": "code_repository_copy",
                    "status": "failed",
                    "detail": f"Copied cached repository from {cached_repo} but destination is not a git repository.",
                }
            )
            _remove_partial_repo(destination)
    else:
        attempts.append(
            {
                "strategy": "code_repository_copy",
                "status": "failed",
                "detail": f"No matching repository was found under {_CODE_REPOSITORY_ROOT}.",
            }
        )

    for strategy, command in (
        ("clone", ["git", "clone", spec.clone_url, str(destination)]),
        (
            "shallow_clone",
            ["git", "clone", "--depth", "1", spec.clone_url, str(destination)],
        ),
    ):
        _remove_partial_repo(destination)
        completed = _run_repo_materialization_command(
            command=command,
            cwd=workspace_root,
            timeout_seconds=_GITHUB_REPO_MATERIALIZE_TIMEOUT_SECONDS,
        )
        if completed.returncode == 0 and _looks_like_git_repo(destination):
            attempts.append(
                {
                    "strategy": strategy,
                    "status": "success",
                    "detail": _trim_repo_materialization_output(
                        completed.stdout, completed.stderr
                    ),
                }
            )
            _write_github_repo_materialization_log(
                log_path,
                {
                    "repo": spec.clone_url,
                    "destination": str(destination),
                    "selected_strategy": strategy,
                    "attempts": attempts,
                },
            )
            return None
        attempts.append(
            {
                "strategy": strategy,
                "status": "failed",
                "detail": _trim_repo_materialization_output(
                    completed.stdout, completed.stderr
                ),
            }
        )

    local_repo = _find_local_repo_for_github_task(
        spec=spec,
        node=node,
        workspace_root=workspace_root,
    )
    if local_repo is not None:
        _remove_partial_repo(destination)
        completed = _run_repo_materialization_command(
            command=[
                "git",
                "clone",
                "--local",
                "--no-hardlinks",
                str(local_repo),
                str(destination),
            ],
            cwd=workspace_root,
            timeout_seconds=_GITHUB_REPO_MATERIALIZE_TIMEOUT_SECONDS,
        )
        if completed.returncode == 0 and _looks_like_git_repo(destination):
            attempts.append(
                {
                    "strategy": "local_clone",
                    "status": "success",
                    "detail": f"Cloned local repository from {local_repo}",
                }
            )
            _write_github_repo_materialization_log(
                log_path,
                {
                    "repo": spec.clone_url,
                    "destination": str(destination),
                    "selected_strategy": "local_clone",
                    "local_repo": str(local_repo),
                    "attempts": attempts,
                },
            )
            return None
        attempts.append(
            {
                "strategy": "local_clone",
                "status": "failed",
                "detail": _trim_repo_materialization_output(
                    completed.stdout, completed.stderr
                ),
            }
        )
    else:
        attempts.append(
            {
                "strategy": "local_clone",
                "status": "failed",
                "detail": "No matching local repository was found.",
            }
        )

    _remove_partial_repo(destination)
    _write_github_repo_materialization_log(
        log_path,
        {
            "repo": spec.clone_url,
            "destination": str(destination),
            "selected_strategy": None,
            "attempts": attempts,
        },
    )
    return WorkerResult(
        status="failed",
        summary=(
            f"Failed to materialize GitHub repository {spec.clone_url} into the workspace. "
            "Cached copy, normal clone, shallow clone, and local-repo fallback all failed."
        ),
        artifacts=[str(log_path)],
        evidence=[
            f"{item['strategy']}: {item['status']} - {item['detail']}"
            for item in attempts
        ],
        next_action_hint=(
            "Provide a local repository path, retry when GitHub access is stable, or adjust the network path."
        ),
        failure_reason="repo_materialization_failed",
    )


async def _invoke_worker_agent(
    *, agent, node: TaskNode, workspace_root: Path
) -> WorkerResult:
    prepared = await asyncio.to_thread(
        _maybe_prepare_worker_inputs,
        node=node,
        workspace_root=workspace_root,
    )
    if prepared is not None:
        return prepared
    if _is_agent_owned_benchmark_case_node(node):
        return await _invoke_worker_runnable(
            agent=agent,
            node=node,
            workspace_root=workspace_root,
        )
    await _maybe_run_agentic_benchmark_case_repair(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )
    deterministic = await asyncio.to_thread(
        _maybe_run_deterministic_worker,
        node=node,
        workspace_root=workspace_root,
    )
    if deterministic is not None:
        return deterministic
    return await _invoke_worker_runnable(
        agent=agent,
        node=node,
        workspace_root=workspace_root,
    )


async def _invoke_worker_runnable(
    *, agent, node: TaskNode, workspace_root: Path
) -> WorkerResult:
    prompt = _build_worker_prompt(node=node, workspace_root=workspace_root)
    invoke_payload, invoke_kwargs = _build_worker_invoke_request(prompt)
    last_error: Exception | None = None
    for attempt in range(_GENERIC_WORKER_TRANSIENT_RETRIES + 1):
        started_at = datetime.now(UTC)
        _append_raw_worker_trace(
            node=node,
            event={
                "event": "worker_invocation_started",
                "node_id": node.node_id,
                "attempt": attempt + 1,
                "started_at": started_at.isoformat(),
                "prompt_mode": _worker_prompt_mode(),
            },
        )
        try:
            messages = await _collect_worker_messages(
                agent=agent,
                invoke_payload=invoke_payload,
                invoke_kwargs=invoke_kwargs,
                node=node,
            )
            _append_raw_worker_message_events(
                node=node, attempt=attempt + 1, messages=messages
            )
            refusal_message = _extract_messages_refusal(messages)
            if refusal_message is not None:
                raise ModelRefusalError(
                    message=refusal_message,
                    stage=f"worker:{node.node_id}",
                    details={"node_id": node.node_id},
                )
            final_text = _last_ai_text(messages)
            parsed = _parse_worker_result(final_text)
            finished_at = datetime.now(UTC)
            model_name, usage = _worker_message_model_and_usage(messages)
            _append_raw_worker_trace(
                node=node,
                event={
                    "event": "worker_invocation_finished",
                    "node_id": node.node_id,
                    "attempt": attempt + 1,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(
                        (finished_at - started_at).total_seconds(), 3
                    ),
                    "model_name": model_name,
                    "usage": usage,
                    "source_urls": _extract_source_urls_from_messages(messages),
                    "raw_output": final_text,
                    "parsed_worker_result": parsed.to_dict(),
                },
            )
            return parsed
        except Exception as exc:
            finished_at = datetime.now(UTC)
            _append_raw_worker_trace(
                node=node,
                event={
                    "event": "worker_invocation_failed",
                    "node_id": node.node_id,
                    "attempt": attempt + 1,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(
                        (finished_at - started_at).total_seconds(), 3
                    ),
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            last_error = exc
            if _should_recover_report_lane_inside_agent(node=node, exc=exc):
                _emit_supervisor_event(
                    kind="worker_recovering_inside_lane",
                    node_id=node.node_id,
                    title=node.title,
                    attempt=attempt + 1,
                    error=f"{type(exc).__name__}: {exc}",
                )
                try:
                    return await _invoke_report_lane_recovery(
                        agent=agent,
                        node=node,
                        workspace_root=workspace_root,
                        base_prompt=prompt,
                        error=exc,
                        failed_attempt=attempt + 1,
                    )
                except Exception as recovery_exc:
                    finished_at = datetime.now(UTC)
                    _append_raw_worker_trace(
                        node=node,
                        event={
                            "event": "worker_lane_recovery_failed",
                            "node_id": node.node_id,
                            "failed_attempt": attempt + 1,
                            "finished_at": finished_at.isoformat(),
                            "error": f"{type(recovery_exc).__name__}: {recovery_exc}",
                        },
                    )
                    last_error = recovery_exc
                    raise
            if (
                attempt >= _GENERIC_WORKER_TRANSIENT_RETRIES
                or not _is_transient_worker_exception(exc)
            ):
                raise
            _emit_supervisor_event(
                kind="worker_retrying",
                node_id=node.node_id,
                title=node.title,
                attempt=attempt + 2,
                error=f"{type(exc).__name__}: {exc}",
            )
            await asyncio.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _should_recover_report_lane_inside_agent(*, node: TaskNode, exc: Exception) -> bool:
    if isinstance(exc, (ModelRefusalError, GraphBubbleUp)):
        return False
    return _is_report_evidence_lane_node(node)


async def _invoke_report_lane_recovery(
    *,
    agent,
    node: TaskNode,
    workspace_root: Path,
    base_prompt: str,
    error: Exception,
    failed_attempt: int,
) -> WorkerResult:
    run_dir = (
        Path(str(node.metadata.get("run_dir", "")))
        if isinstance(node.metadata, dict)
        else Path()
    )
    raw_trace_path = (
        run_dir / "raw_worker_traces" / f"{node.node_id}.jsonl" if run_dir else Path()
    )
    tool_activity_path = run_dir / "tool_activity.jsonl" if run_dir else Path()
    recovery_prompt = (
        f"{base_prompt}\n\n"
        "Report lane recovery instruction:\n"
        f"- The previous attempt for this same lane hit a recoverable tool/runtime error: {type(error).__name__}: {error}\n"
        "- Do not abandon the lane because one tool call, URL, or source failed.\n"
        "- Treat the failed URL/tool/source as unavailable, choose an alternate official source when reasonable, or record a precise evidence gap.\n"
        "- Use evidence already collected in the previous attempt when possible; inspect the raw trace or tool activity only if needed.\n"
        f"- Previous raw trace path: {raw_trace_path}\n"
        f"- Tool activity path: {tool_activity_path}\n"
        "- Complete the assigned lane brief with the best available evidence. Return status completed if the minimum lane brief is usable; return partial only if a material evidence gap remains after recovery.\n"
    )
    invoke_payload, invoke_kwargs = _build_worker_invoke_request(recovery_prompt)
    started_at = datetime.now(UTC)
    _append_raw_worker_trace(
        node=node,
        event={
            "event": "worker_lane_recovery_started",
            "node_id": node.node_id,
            "failed_attempt": failed_attempt,
            "started_at": started_at.isoformat(),
            "error": f"{type(error).__name__}: {error}",
        },
    )
    messages = await _collect_worker_messages(
        agent=agent,
        invoke_payload=invoke_payload,
        invoke_kwargs=invoke_kwargs,
        node=node,
    )
    _append_raw_worker_message_events(
        node=node, attempt=failed_attempt + 1, messages=messages
    )
    refusal_message = _extract_messages_refusal(messages)
    if refusal_message is not None:
        raise ModelRefusalError(
            message=refusal_message,
            stage=f"worker:{node.node_id}:recovery",
            details={"node_id": node.node_id},
        )
    final_text = _last_ai_text(messages)
    parsed = _parse_worker_result(final_text)
    finished_at = datetime.now(UTC)
    model_name, usage = _worker_message_model_and_usage(messages)
    _append_raw_worker_trace(
        node=node,
        event={
            "event": "worker_lane_recovery_finished",
            "node_id": node.node_id,
            "failed_attempt": failed_attempt,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
            "model_name": model_name,
            "usage": usage,
            "source_urls": _extract_source_urls_from_messages(messages),
            "raw_output": final_text,
            "parsed_worker_result": parsed.to_dict(),
        },
    )
    return parsed


async def _collect_worker_messages(
    *,
    agent,
    invoke_payload: dict[str, object],
    invoke_kwargs: dict[str, object],
    node: TaskNode,
) -> list[object]:
    astream = getattr(agent, "astream", None)
    if not callable(astream):
        result = await agent.ainvoke(invoke_payload, **invoke_kwargs)
        messages = result.get("messages", []) if isinstance(result, dict) else []
        _record_worker_tool_events(node=node, messages=messages)
        return messages

    stream = astream(
        invoke_payload,
        stream_mode=["messages"],
        subgraphs=True,
        **invoke_kwargs,
    )
    if not hasattr(stream, "__aiter__"):
        if inspect.isawaitable(stream) and hasattr(stream, "close"):
            stream.close()
        result = await agent.ainvoke(invoke_payload, **invoke_kwargs)
        messages = result.get("messages", []) if isinstance(result, dict) else []
        _record_worker_tool_events(node=node, messages=messages)
        return messages

    messages: list[object] = []
    tool_state = _WorkerToolEventState()
    async for chunk in stream:
        if not isinstance(chunk, tuple) or len(chunk) != 3:  # noqa: PLR2004
            continue
        _namespace, stream_mode, data = chunk
        if stream_mode != "messages":
            continue
        if not isinstance(data, tuple) or len(data) != 2:  # noqa: PLR2004
            continue
        message, metadata = data
        if isinstance(metadata, dict) and metadata.get("lc_source") == "summarization":
            continue
        messages.append(message)
        _record_worker_tool_events(node=node, messages=[message], state=tool_state)
    return messages


@dataclass(slots=True)
class _WorkerToolEventState:
    tool_names_by_id: dict[str, str]
    pending_tool_calls: list[dict[str, object]]
    seen_tool_call_keys: set[str]
    seen_tool_result_keys: set[str]

    def __init__(self) -> None:
        self.tool_names_by_id = {}
        self.pending_tool_calls = []
        self.seen_tool_call_keys = set()
        self.seen_tool_result_keys = set()


def _record_worker_tool_events(
    *,
    node: TaskNode,
    messages: list[object],
    state: _WorkerToolEventState | None = None,
) -> _WorkerToolEventState:
    """Expose internal worker/subagent tool calls through supervisor events."""
    tool_state = state or _WorkerToolEventState()
    for message in messages:
        for tool_call in _message_tool_calls(message):
            event = _worker_tool_call_event_from_chunk(
                node=node,
                tool_call=tool_call,
                state=tool_state,
            )
            if event is not None:
                _emit_worker_tool_call_event(node=node, event=event, state=tool_state)

        tool_result = _message_tool_result(message, tool_state.tool_names_by_id)
        if tool_result is None:
            continue
        pending_event = _pending_tool_call_event_for_result(
            node=node,
            tool_call_id=str(tool_result.get("tool_call_id", "") or ""),
            state=tool_state,
        )
        if pending_event is not None:
            _emit_worker_tool_call_event(
                node=node, event=pending_event, state=tool_state
            )
        event = {
            "event": "worker_tool_result",
            "node_id": node.node_id,
            **tool_result,
        }
        event_key = json.dumps(event, sort_keys=True, ensure_ascii=False)
        if event_key in tool_state.seen_tool_result_keys:
            continue
        tool_state.seen_tool_result_keys.add(event_key)
        _append_worker_tool_activity(node=node, event=event)
        _emit_supervisor_event(kind="worker_tool_result", **event)
    return tool_state


def _worker_tool_call_event_from_chunk(
    *,
    node: TaskNode,
    tool_call: dict[str, object],
    state: _WorkerToolEventState,
) -> dict[str, object] | None:
    """Merge streamed tool-call name/id and argument chunks before logging."""

    tool_call_id = str(tool_call.get("id") or "")
    tool_name = str(tool_call.get("name") or "")
    args = tool_call.get("args")
    has_args = args not in (None, "", {})
    if tool_call_id and tool_name:
        state.tool_names_by_id[tool_call_id] = tool_name
        pending = {
            "node_id": node.node_id,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "args": args if has_args else {},
            "emitted": False,
        }
        state.pending_tool_calls.append(pending)
        if has_args:
            pending["emitted"] = True
            return _tool_call_event_from_pending(pending)
        return None

    if has_args and not tool_name and not tool_call_id:
        for pending in reversed(state.pending_tool_calls):
            if pending.get("emitted") is True:
                continue
            pending["args"] = args
            pending["emitted"] = True
            return _tool_call_event_from_pending(pending)

    if tool_name or tool_call_id or has_args:
        resolved_name = tool_name or (
            state.tool_names_by_id.get(tool_call_id, "") if tool_call_id else ""
        )
        return {
            "event": "worker_tool_call",
            "node_id": node.node_id,
            "tool_name": resolved_name or "unknown",
            "tool_call_id": tool_call_id,
            "args_preview": _compact_event_value(args),
        }
    return None


def _pending_tool_call_event_for_result(
    *,
    node: TaskNode,
    tool_call_id: str,
    state: _WorkerToolEventState,
) -> dict[str, object] | None:
    if not tool_call_id:
        return None
    for pending in reversed(state.pending_tool_calls):
        if (
            pending.get("tool_call_id") != tool_call_id
            or pending.get("emitted") is True
        ):
            continue
        pending["emitted"] = True
        pending["node_id"] = node.node_id
        return _tool_call_event_from_pending(pending)
    return None


def _tool_call_event_from_pending(pending: dict[str, object]) -> dict[str, object]:
    return {
        "event": "worker_tool_call",
        "node_id": str(pending.get("node_id", "")),
        "tool_name": str(pending.get("tool_name", "") or "unknown"),
        "tool_call_id": str(pending.get("tool_call_id", "") or ""),
        "args_preview": _compact_event_value(pending.get("args")),
    }


def _emit_worker_tool_call_event(
    *,
    node: TaskNode,
    event: dict[str, object],
    state: _WorkerToolEventState,
) -> None:
    event_key = json.dumps(event, sort_keys=True, ensure_ascii=False)
    if event_key in state.seen_tool_call_keys:
        return
    state.seen_tool_call_keys.add(event_key)
    _append_worker_tool_activity(node=node, event=event)
    _emit_supervisor_event(kind="worker_tool_call", **event)


def _extract_messages_refusal(messages: list[object]) -> str | None:
    for message in messages:
        refusal_message = _extract_model_refusal_message(message)
        if refusal_message is not None:
            return refusal_message
    return None


def _message_tool_calls(message: object) -> list[dict[str, object]]:
    tool_calls = getattr(message, "tool_calls", None)
    normalized_calls = (
        [item for item in tool_calls if isinstance(item, dict)]
        if isinstance(tool_calls, list)
        else []
    )
    if normalized_calls:
        return normalized_calls
    content_blocks = getattr(message, "content_blocks", None)
    if not isinstance(content_blocks, list):
        return []
    block_calls: list[dict[str, object]] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_call":
            continue
        tool_name = block.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        block_calls.append(
            {
                "id": block.get("id"),
                "name": tool_name,
                "args": block.get("args"),
            }
        )
    return block_calls


def _message_tool_result(
    message: object,
    tool_names_by_id: dict[str, str],
) -> dict[str, object] | None:
    if not isinstance(message, ToolMessage):
        return None
    tool_call_id = str(getattr(message, "tool_call_id", "") or "")
    tool_name = str(
        getattr(message, "name", "") or tool_names_by_id.get(tool_call_id, "unknown")
    )
    status = str(getattr(message, "status", "") or "success")
    return {
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "status": status,
        "result_preview": _compact_event_value(getattr(message, "content", "")),
    }


def _append_worker_tool_activity(*, node: TaskNode, event: dict[str, object]) -> None:
    run_dir_raw = (
        node.metadata.get("run_dir") if isinstance(node.metadata, dict) else None
    )
    if not isinstance(run_dir_raw, str) or not run_dir_raw:
        return
    try:
        _append_tool_activity_event(run_dir=Path(run_dir_raw), event=event)
    except OSError:
        return


def _append_tool_activity_event(*, run_dir: Path, event: dict[str, object]) -> None:
    activity_path = run_dir / "tool_activity.jsonl"
    with activity_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _raw_worker_trace_enabled() -> bool:
    value = (get_env(SUPERVISOR_RAW_WORKER_TRACE_ENV, "1") or "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _raw_worker_trace_path(node: TaskNode) -> Path | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    run_dir_raw = metadata.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        return None
    safe_node_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", node.node_id).strip("._")
    if not safe_node_id:
        safe_node_id = "worker"
    return Path(run_dir_raw) / "raw_worker_traces" / f"{safe_node_id}.jsonl"


def _append_raw_worker_trace(*, node: TaskNode, event: dict[str, object]) -> None:
    if not _raw_worker_trace_enabled():
        return
    path = _raw_worker_trace_path(node)
    if path is None:
        return
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(),
        **event,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_json_safe(payload), ensure_ascii=False) + "\n")
    except OSError:
        return


def _append_raw_worker_message_events(
    *,
    node: TaskNode,
    attempt: int,
    messages: list[object],
) -> None:
    for index, message in enumerate(messages):
        _append_raw_worker_trace(
            node=node,
            event={
                "event": "worker_message",
                "node_id": node.node_id,
                "attempt": attempt,
                "message_index": index,
                "message": _serialize_worker_message(message),
            },
        )


def _serialize_worker_message(message: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "class": type(message).__name__,
        "type": str(getattr(message, "type", "") or ""),
        "content": getattr(message, "content", None),
    }
    for attr in (
        "name",
        "id",
        "tool_call_id",
        "status",
        "tool_calls",
        "invalid_tool_calls",
        "additional_kwargs",
        "response_metadata",
        "usage_metadata",
    ):
        value = getattr(message, attr, None)
        if value not in (None, "", [], {}):
            payload[attr] = value
    return _json_safe(payload)


def _worker_message_model_and_usage(
    messages: list[object],
) -> tuple[str | None, dict[str, object] | None]:
    model_name: str | None = None
    usage: dict[str, object] | None = None
    for message in reversed(messages):
        response_metadata = getattr(message, "response_metadata", None)
        if isinstance(response_metadata, dict) and model_name is None:
            provider = str(response_metadata.get("model_provider", "") or "").strip()
            name = str(
                response_metadata.get("model_name", "")
                or response_metadata.get("model", "")
                or ""
            ).strip()
            if provider and name:
                model_name = f"{provider}:{name}"
            elif name:
                model_name = name
        usage_metadata = getattr(message, "usage_metadata", None)
        if isinstance(usage_metadata, dict) and usage is None:
            usage = {
                str(key): _json_safe(value) for key, value in usage_metadata.items()
            }
        if model_name is not None and usage is not None:
            break
    return model_name, usage


def _extract_source_urls_from_messages(messages: list[object]) -> list[str]:
    urls: list[str] = []
    for message in messages:
        urls.extend(
            _extract_source_urls_from_object(_serialize_worker_message(message))
        )
    return _dedupe_urls(urls)


def _extract_source_urls_from_object(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        urls.extend(_extract_urls_from_text(value))
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                urls.extend(_extract_source_urls_from_object(json.loads(stripped)))
            except json.JSONDecodeError:
                pass
        return _dedupe_urls(urls)
    if isinstance(value, dict):
        for item in value.values():
            urls.extend(_extract_source_urls_from_object(item))
        return _dedupe_urls(urls)
    if isinstance(value, (list, tuple, set)):
        for item in value:
            urls.extend(_extract_source_urls_from_object(item))
        return _dedupe_urls(urls)
    return []


def _extract_urls_from_text(text: str) -> list[str]:
    urls = []
    for match in _URL_RE.findall(text):
        candidate = match.rstrip(".,;:]}）】")
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(candidate)
    return _dedupe_urls(urls)


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _finalize_refusal_run(
    *,
    run_dir: Path,
    task: str,
    task_type: str,
    rounds,
    refusal: ModelRefusalError,
) -> SupervisorRunResult:
    final_decision = SupervisorDecision(
        decision="stop",
        reason=f"model_refusal:{refusal.stage}",
    )
    final_summary = (
        "# Supervisor Summary\n\n"
        f"- Task: {task}\n"
        "- Decision: stop\n"
        f"- Reason: model refusal during {refusal.stage}\n"
    )
    user_response = _relativize_user_facing_paths(refusal.user_message, run_dir=run_dir)
    (run_dir / "final_summary.md").write_text(final_summary, encoding="utf-8")
    (run_dir / "final_response.md").write_text(user_response, encoding="utf-8")
    _write_json(
        run_dir / "final_decision.json",
        {
            "decision": final_decision.decision,
            "reason": final_decision.reason,
            "failed_nodes": [],
            "task_type": task_type,
            "generic_approach": None,
            "round_count": len(rounds),
            "run_dir": str(run_dir),
            "final_response_path": str(run_dir / "final_response.md"),
            "refusal_details": refusal.details,
        },
    )
    _write_supervisor_evaluation(run_dir)
    _emit_supervisor_event(
        kind="run_finished",
        decision=final_decision.decision,
        reason=final_decision.reason,
        failed_nodes=[],
        generic_approach=None,
        round_count=len(rounds),
        run_dir=str(run_dir),
    )
    return SupervisorRunResult(
        run_dir=run_dir,
        final_summary=final_summary,
        user_response=user_response,
        final_decision=final_decision,
        round_count=len(rounds),
    )


def _write_supervisor_evaluation(run_dir: Path) -> None:
    try:
        result = write_evaluation_for_run(run_dir)
    except Exception as exc:
        _write_json(
            run_dir / "evaluation.json",
            {
                "task_family": "unknown",
                "completion_status": "invalid",
                "completion_level": "evaluation_failed",
                "false_positive": False,
                "unsupported_claims": [],
                "evidence_paths": [],
                "required_evidence_missing": ["evaluation could not be computed"],
                "failure_stage": "evaluation",
                "failure_reason": f"{type(exc).__name__}: {exc}",
                "reproducible": False,
            },
        )
        return
    _emit_supervisor_event(
        kind="run_evaluated",
        run_dir=str(run_dir),
        task_family=result.task_family,
        completion_status=result.completion_status,
        completion_level=result.completion_level,
        false_positive=result.false_positive,
    )


def _compact_event_value(value: object, *, max_chars: int = 500) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _build_worker_invoke_request(
    prompt: str,
) -> tuple[dict[str, list[HumanMessage | SystemMessage]], dict[str, object]]:
    """Build the nested worker-agent request in the configured prompt mode."""
    mode = _worker_prompt_mode()
    user_message = HumanMessage(
        content="Execute the assigned node and return the required JSON only."
    )
    if mode == "messages":
        return (
            {
                "messages": [
                    SystemMessage(content=prompt),
                    user_message,
                ]
            },
            {},
        )
    return (
        {
            "messages": [user_message],
        },
        {"context": {"system_prompt": prompt}},
    )


def _worker_prompt_mode() -> str:
    return (
        (
            get_env(
                _WORKER_PROMPT_MODE_ENV,
                _DEFAULT_WORKER_PROMPT_MODE,
            )
            or _DEFAULT_WORKER_PROMPT_MODE
        )
        .strip()
        .lower()
    )


def _maybe_run_deterministic_worker(
    *, node: TaskNode, workspace_root: Path
) -> WorkerResult | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if metadata.get("task_type") != "benchmark":
        return None
    if node.node_id in {"register", "retry_register"}:
        return _run_deterministic_benchmark_register(
            node=node, workspace_root=workspace_root
        )
    if node.node_id == "summarize":
        return _run_deterministic_benchmark_summary(
            node=node, workspace_root=workspace_root
        )
    if _looks_like_user_delivery_node(node.node_id):
        return None
    if _is_agent_owned_benchmark_case_node(node):
        return None
    repo = _benchmark_repo_from_node_id(node.node_id)
    if repo is not None:
        return _run_deterministic_benchmark_case(
            node=node,
            workspace_root=workspace_root,
            repo=repo,
        )
    return None


def _is_agent_owned_benchmark_case_node(node: TaskNode) -> bool:
    """Return True when a benchmark per-operator node should be owned by an agent.

    Register and summarize remain deterministic orchestration adapters, but the
    actual per-operator case execution is an agent responsibility. The agent may
    still choose to run the checked-in helper command as one tool action, but
    supervisor no longer short-circuits the whole case through helper code.
    """

    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if metadata.get("task_type") != "benchmark":
        return False
    if node.node_id in {"register", "retry_register", "summarize"}:
        return False
    if _looks_like_user_delivery_node(node.node_id):
        return False
    return _benchmark_repo_from_node_id(node.node_id) is not None


async def _maybe_run_agentic_benchmark_register(
    *,
    agent,
    node: TaskNode,
    workspace_root: Path,
) -> WorkerResult | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if metadata.get("task_type") != "benchmark":
        return None
    if node.node_id not in {"register", "retry_register"}:
        return None
    if not _benchmark_register_agentic_selection_enabled():
        return None
    requested_tools = [
        str(item)
        for item in metadata.get("selected_tools", [])
        if isinstance(item, str) and item.strip()
    ]
    if requested_tools:
        return None
    if agent is None:
        return None
    task = str(metadata.get("task", "")).strip()
    benchmark_root = str(metadata.get("benchmark_root", "")).strip()
    excluded_tools = {
        str(item)
        for item in metadata.get("excluded_tools", [])
        if isinstance(item, str) and item.strip()
    }
    if not task or not _candidate_operator_store_roots(workspace_root):
        return None
    agent_selection, debug_payload = await _select_benchmark_tools_with_agent(
        agent=agent,
        task=task,
        workspace_root=workspace_root,
        excluded_tools=excluded_tools,
        benchmark_root=benchmark_root,
    )
    if agent_selection is None:
        debug_path = _write_benchmark_register_agentic_debug(
            node=node,
            payload=debug_payload,
        )
        artifacts = [debug_path] if debug_path else []
        evidence = [debug_path] if debug_path else []
        return WorkerResult(
            status="blocked",
            summary=(
                "Agent-driven benchmark registration could not choose a shared dataset "
                "and compatible tool subset."
            ),
            artifacts=artifacts,
            evidence=evidence,
            next_action_hint=(
                "Inspect the agentic register debug artifact, then tighten the prompt or "
                "relax the candidate set as needed."
            ),
            failure_reason="agentic_register_selection_failed",
        )
    override_metadata = dict(metadata)
    override_metadata["_selection_override"] = agent_selection
    selected_tools = agent_selection.get("selected_tools")
    if not isinstance(selected_tools, list):
        return None
    selected_node = TaskNode(
        node_id=node.node_id,
        title=node.title,
        objective=node.objective,
        capability_bundles=list(node.capability_bundles),
        metadata=override_metadata,
    )
    return await asyncio.to_thread(
        _run_deterministic_benchmark_register,
        node=selected_node,
        workspace_root=workspace_root,
    )


def _write_benchmark_register_agentic_debug(
    *,
    node: TaskNode,
    payload: dict[str, object],
) -> str | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    run_dir_raw = metadata.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        return None
    path = Path(run_dir_raw) / "register_agentic_selection_debug.json"
    try:
        _write_json(path, payload)
    except OSError:
        return None
    return str(path)


def _benchmark_case_agentic_repair_enabled() -> bool:
    value = (
        get_env(
            _BENCHMARK_CASE_AGENTIC_REPAIR_ENV,
            _DEFAULT_BENCHMARK_CASE_AGENTIC_REPAIR,
        )
        or _DEFAULT_BENCHMARK_CASE_AGENTIC_REPAIR
    ).strip()
    return value.lower() not in {"0", "false", "no", "off"}


async def _maybe_run_agentic_benchmark_case_repair(
    *,
    agent,
    node: TaskNode,
    workspace_root: Path,
) -> dict[str, object] | None:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if metadata.get("task_type") != "benchmark":
        return None
    if not node.node_id.startswith("retry_"):
        return None
    if not _benchmark_case_agentic_repair_enabled():
        return None
    if agent is None:
        return None
    repo = _benchmark_repo_from_node_id(node.node_id)
    if repo is None:
        return None
    run_dir_raw = metadata.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        return None
    run_dir = Path(run_dir_raw)
    case_dir = run_dir / "cases" / repo
    ready_path = case_dir / "execution_ready.json"
    manifest_path = case_dir / "manifest.json"
    if not ready_path.exists() or not manifest_path.exists():
        return None
    ready_payload = _read_json_file(ready_path)
    manifest_payload = _read_json_file(manifest_path)
    if not isinstance(ready_payload, dict) or not isinstance(manifest_payload, dict):
        return None
    wdl_path = str(ready_payload.get("wdl_path", "")).strip()
    inputs_json_path = str(ready_payload.get("inputs_json_path", "")).strip()
    if not wdl_path or not Path(wdl_path).exists():
        return None
    repair_prompt = _build_benchmark_case_repair_prompt(
        repo=repo,
        task=str(metadata.get("task", "")).strip(),
        case_dir=case_dir,
        manifest_payload=manifest_payload,
        ready_payload=ready_payload,
    )
    invoke_payload, invoke_kwargs = _build_worker_invoke_request(repair_prompt)
    try:
        result = await agent.ainvoke(invoke_payload, **invoke_kwargs)
    except (TypeError, ValueError):
        try:
            result = await agent.ainvoke(
                [
                    SystemMessage(content=repair_prompt),
                    HumanMessage(content="Return JSON only after any file edits."),
                ]
            )
        except Exception:
            return None
    except Exception:
        return None
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if messages:
        _record_worker_tool_events(node=node, messages=messages)
        refusal_message = _extract_messages_refusal(messages)
        if refusal_message is not None:
            return None
        text = _last_ai_text(messages)
        usage_metadata = getattr(messages[-1], "usage_metadata", None)
        usage = usage_metadata if isinstance(usage_metadata, dict) else None
    else:
        refusal_message = _extract_model_refusal_message(result)
        if refusal_message is not None:
            return None
        text = _message_text(result)
        usage_metadata = getattr(result, "usage_metadata", None)
        usage = usage_metadata if isinstance(usage_metadata, dict) else None
    parsed = _extract_generic_json_payload(text)
    if parsed is None:
        return None
    modified_files = [
        str(item).strip()
        for item in parsed.get("modified_files", [])
        if isinstance(item, str) and str(item).strip()
    ]
    report = {
        "repo": repo,
        "node_id": node.node_id,
        "repaired": bool(parsed.get("repaired")),
        "modified_files": modified_files,
        "summary": str(parsed.get("summary", "")).strip(),
        "raw_output": text,
        "usage": usage,
        "wdl_path": wdl_path,
        "inputs_json_path": inputs_json_path,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_json(case_dir / "repair_report.json", report)
    _append_worker_tool_activity(
        node=node,
        event={
            "event": "benchmark_case_repair",
            "node_id": node.node_id,
            "repo": repo,
            "repaired": report["repaired"],
            "modified_files": modified_files,
            "summary": report["summary"],
        },
    )
    return report


def _read_json_file(path: Path) -> dict[str, object] | list[object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, (dict, list)) else None


def _latest_benchmark_wdl_workflow_dir(case_dir: Path) -> Path | None:
    wdl_dir = case_dir / "wdl"
    if not wdl_dir.exists():
        return None
    candidates = [path for path in wdl_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _latest_file_matching(root: Path, pattern: str) -> Path | None:
    candidates = [path for path in root.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _read_text_excerpt(path: Path | None, *, max_chars: int = 4000) -> str:
    if path is None:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _run_deterministic_benchmark_register(
    *, node: TaskNode, workspace_root: Path
) -> WorkerResult:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    run_dir_raw = metadata.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        return WorkerResult(
            status="failed",
            summary="Benchmark register helper is missing run_dir metadata.",
            failure_reason="missing_run_dir",
        )
    selected_tools = [
        str(item)
        for item in metadata.get("selected_tools", [])
        if isinstance(item, str) and item.strip()
    ]
    excluded_tools = {
        str(item)
        for item in metadata.get("excluded_tools", [])
        if isinstance(item, str) and item.strip()
    }
    benchmark_root_raw = metadata.get("benchmark_root")
    benchmark_root = (
        benchmark_root_raw.strip() if isinstance(benchmark_root_raw, str) else ""
    )
    violating_requested_tools = [
        tool for tool in selected_tools if tool in excluded_tools
    ]
    if violating_requested_tools:
        return WorkerResult(
            status="failed",
            summary=(
                "Benchmark register selected tools that violate the user's explicit "
                f"exclusion constraint: {', '.join(violating_requested_tools)}."
            ),
            failure_reason="selected_tools_violate_exclusion_constraint",
        )
    task = str(metadata.get("task", "")).strip()
    run_dir = Path(run_dir_raw)
    selection_override = (
        metadata.get("_selection_override")
        if isinstance(metadata.get("_selection_override"), dict)
        else None
    )
    selected_tools, selection_report = _resolve_benchmark_selected_tools(
        task=task,
        workspace_root=workspace_root,
        benchmark_root=benchmark_root,
        requested_tools=selected_tools,
        excluded_tools=excluded_tools,
        selection_override=selection_override,
    )
    selection_dataset_key = str(selection_report.get("dataset_key", "")).strip()
    selection_dataset_strategy = str(
        selection_report.get("dataset_strategy", "")
    ).strip() or _benchmark_dataset_strategy_for_task(task)
    selection_report["dataset_strategy"] = selection_dataset_strategy
    if (
        selection_dataset_strategy == "shared_dataset"
        and not selection_dataset_key
        and selected_tools
    ):
        dataset_candidate = _resolve_benchmark_dataset_candidate(
            task=task,
            workspace_root=workspace_root,
            operator_candidates=_collect_benchmark_operator_candidates(
                task=task,
                workspace_root=workspace_root,
                excluded_tools=excluded_tools,
                limit=_BENCHMARK_REGISTER_AGENTIC_CANDIDATE_LIMIT,
            ),
            requested_tools=selected_tools,
            excluded_tools=excluded_tools,
            benchmark_root=benchmark_root,
        )
        if dataset_candidate is not None:
            selection_dataset_key = str(dataset_candidate.get("dataset_id", "")).strip()
            if selection_dataset_key:
                selection_report["dataset_key"] = selection_dataset_key
                if not isinstance(selection_report.get("selected_dataset"), dict):
                    selection_report["selected_dataset"] = dataset_candidate
    selection_report_path = run_dir / "operator_selection.json"
    _write_json(selection_report_path, selection_report)
    if not selected_tools:
        if not excluded_tools and not benchmark_root and _task_contains_url(task):
            return WorkerResult(
                status="failed",
                summary=(
                    "Benchmark register could not find local benchmark assets for the provided URLs. "
                    "URL-only benchmark requests need a preparation step that clones/builds tools and "
                    "materializes WDL/input assets before tool selection can run."
                ),
                failure_reason="missing_benchmark_assets",
                next_action_hint="prepare_benchmark_assets_from_urls",
            )
        return WorkerResult(
            status="failed",
            summary="Benchmark register could not resolve any matching operators from the local operator store or benchmark catalog.",
            failure_reason="missing_selected_tools",
            artifacts=[str(selection_report_path)],
        )
    violating_tools = [tool for tool in selected_tools if tool in excluded_tools]
    if violating_tools:
        return WorkerResult(
            status="failed",
            summary=(
                "Benchmark register selected tools that violate the user's explicit "
                f"exclusion constraint: {', '.join(violating_tools)}."
            ),
            failure_reason="selected_tools_violate_exclusion_constraint",
            artifacts=[str(selection_report_path)],
        )
    selected_operators = [
        item
        for item in selection_report.get("selected_operators", [])
        if isinstance(item, dict)
    ]
    repo_root: Path | None = None
    if selected_operators:
        command_results = _materialize_benchmark_selection_cases(
            run_dir=run_dir,
            task=task,
            workspace_root=workspace_root,
            benchmark_root=benchmark_root,
            selected_tools=selected_tools,
            selected_operators=selected_operators,
            selection_report=selection_report,
        )
        _write_json(selection_report_path, selection_report)
    else:
        return WorkerResult(
            status="failed",
            summary=(
                "Benchmark register selected tools but could not materialize runnable operator "
                "records for them after helper removal."
            ),
            failure_reason="missing_selected_operator_records",
            artifacts=[str(selection_report_path)],
        )

    metric_plan = _write_metric_plan(run_dir=run_dir, selected_tools=selected_tools)
    readiness_rows: list[dict[str, object]] = []
    artifacts = [
        str(selection_report_path),
        str(run_dir / "benchmark_plan.json"),
        str(run_dir / "benchmark_plan.md"),
        str(run_dir / "dataset_resolution.json"),
        str(run_dir / "dataset_resolution.md"),
        str(run_dir / "metric_plan.json"),
        str(run_dir / "metric_plan.md"),
    ]
    shared_datasets: list[str] = []
    all_ready = True
    ready_tools: list[str] = []
    blocked_tools: list[str] = []
    for repo in selected_tools:
        case_dir = run_dir / "cases" / repo
        manifest_path = case_dir / "manifest.json"
        ready_path = case_dir / "execution_ready.json"
        dataset_selection_path = case_dir / "dataset_selection.json"
        dataset_manifest_path = case_dir / "dataset_manifest.json"
        agent_task_path = case_dir / "agent_task.md"
        case_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ready_payload = json.loads(ready_path.read_text(encoding="utf-8"))
        dataset_key = str(case_manifest.get("dataset_key", ""))
        if dataset_key and dataset_key not in shared_datasets:
            shared_datasets.append(dataset_key)
        ready = bool(ready_payload.get("ready"))
        all_ready = all_ready and ready
        if ready:
            ready_tools.append(repo)
        else:
            blocked_tools.append(repo)
        readiness_rows.append(
            {
                "repo": repo,
                "dataset_key": dataset_key,
                "ready": ready,
                "runtime_image": ready_payload.get("runtime_image"),
                "wdl_path": ready_payload.get("wdl_path"),
                "inputs_json_path": ready_payload.get("inputs_json_path"),
            }
        )
        artifacts.extend(
            [
                str(dataset_selection_path),
                str(dataset_manifest_path),
                str(agent_task_path),
                str(ready_path),
            ]
        )
    register_report = {
        "task": task,
        "repo_root": str(repo_root) if repo_root is not None else "",
        "run_dir": str(run_dir),
        "selected_tools": selected_tools,
        "selection_strategy": selection_report.get("selection_strategy"),
        "selection_dataset_strategy": selection_report.get("dataset_strategy"),
        "selection_dataset_key": selection_report.get("dataset_key"),
        "tool_dataset_keys": selection_report.get("tool_dataset_keys", {}),
        "selection_allowed_tools": selection_report.get("allowed_tools"),
        "ready_tools": ready_tools,
        "blocked_tools": blocked_tools,
        "shared_datasets": shared_datasets,
        "metric_plan": metric_plan,
        "readiness": readiness_rows,
        "command_results": command_results,
    }
    _write_json(run_dir / "register_report.json", register_report)
    artifacts.append(str(run_dir / "register_report.json"))
    operator_artifacts = _materialize_benchmark_operator_products(
        run_dir=run_dir,
        selected_tools=selected_tools,
        source_repo="",
    )
    artifacts.extend(operator_artifacts)
    if shared_datasets:
        dataset_summary = ", ".join(shared_datasets)
    else:
        dataset_summary = "unknown dataset"
    tool_summary = ", ".join(selected_tools)
    if all_ready:
        return WorkerResult(
            status="completed",
            summary=f"Registered benchmark subset for {dataset_summary}: {tool_summary}.",
            artifacts=artifacts,
            evidence=[str(run_dir / "register_report.json")],
            spawned_subgraph={
                "selected_tools": selected_tools,
                "ready_tools": ready_tools,
                "blocked_tools": blocked_tools,
                "dataset_keys": shared_datasets,
                "register_report": str(run_dir / "register_report.json"),
            },
        )
    if ready_tools:
        ready_summary = ", ".join(ready_tools)
        blocked_summary = ", ".join(blocked_tools) if blocked_tools else "none"
        return WorkerResult(
            status="partial",
            summary=(
                f"Registered benchmark subset for {dataset_summary}; ready tools: "
                f"{ready_summary}; blocked tools: {blocked_summary}."
            ),
            artifacts=artifacts,
            evidence=[str(run_dir / "register_report.json")],
            failure_reason="execution_ready_incomplete",
            next_action_hint=(
                "Proceed with ready benchmark tools and report blocked tools separately."
            ),
            spawned_subgraph={
                "selected_tools": ready_tools,
                "registered_tools": selected_tools,
                "ready_tools": ready_tools,
                "blocked_tools": blocked_tools,
                "dataset_keys": shared_datasets,
                "register_report": str(run_dir / "register_report.json"),
            },
        )
    return WorkerResult(
        status="partial",
        summary=f"Registered benchmark subset for {dataset_summary}, but some execution-ready artifacts are still incomplete: {tool_summary}.",
        artifacts=artifacts,
        evidence=[str(run_dir / "register_report.json")],
        failure_reason="execution_ready_incomplete",
        spawned_subgraph={
            "selected_tools": [],
            "registered_tools": selected_tools,
            "ready_tools": ready_tools,
            "blocked_tools": blocked_tools,
            "dataset_keys": shared_datasets,
            "register_report": str(run_dir / "register_report.json"),
        },
    )


async def _select_benchmark_tools_with_agent(
    *,
    agent,
    task: str,
    workspace_root: Path,
    excluded_tools: set[str],
    benchmark_root: str = "",
) -> tuple[dict[str, object] | None, dict[str, object]]:
    candidates = _collect_benchmark_operator_candidates(
        task=task,
        workspace_root=workspace_root,
        excluded_tools=excluded_tools,
        limit=_BENCHMARK_REGISTER_AGENTIC_CANDIDATE_LIMIT,
    )
    debug_payload: dict[str, object] = {
        "task": task,
        "benchmark_root": benchmark_root,
        "excluded_tools": sorted(excluded_tools),
        "operator_store_roots": [
            str(path) for path in _candidate_operator_store_roots(workspace_root)
        ],
        "dataset_store_roots": [
            str(path) for path in _candidate_dataset_store_roots(workspace_root)
        ],
        "candidate_names": [
            str(item.get("name", "")).strip()
            for item in candidates
            if str(item.get("name", "")).strip()
        ],
    }
    if not candidates:
        debug_payload["failure_stage"] = "collect_candidates"
        debug_payload["failure_reason"] = "no_candidates"
        return None, debug_payload
    if _benchmark_dataset_strategy_for_task(task) == "per_operator_dataset":
        return await _select_benchmark_tools_with_agent_exploratory(
            agent=agent,
            task=task,
            workspace_root=workspace_root,
            candidates=candidates,
            excluded_tools=excluded_tools,
            benchmark_root=benchmark_root,
            debug_payload=debug_payload,
        )
    dataset_options = _benchmark_register_agent_dataset_options(
        task=task,
        workspace_root=workspace_root,
        operator_candidates=candidates,
        excluded_tools=excluded_tools,
        benchmark_root=benchmark_root,
    )
    if not dataset_options:
        ranked_dataset_candidates = _rank_local_dataset_store_candidates(
            task=task,
            workspace_root=workspace_root,
            limit=12,
        )
        debug_payload["ranked_dataset_ids"] = [
            str(item.get("dataset_id", "")).strip()
            for item in ranked_dataset_candidates
            if str(item.get("dataset_id", "")).strip()
        ]
        fallback_dataset = _resolve_benchmark_dataset_candidate(
            task=task,
            workspace_root=workspace_root,
            operator_candidates=candidates,
            requested_tools=[],
            excluded_tools=excluded_tools,
            benchmark_root=benchmark_root,
        )
        if fallback_dataset is not None:
            dataset_options = [fallback_dataset]
            debug_payload["dataset_option_fallback"] = [
                str(fallback_dataset.get("dataset_id", "")).strip()
            ]
        elif ranked_dataset_candidates:
            generic_ranked = [
                item
                for item in ranked_dataset_candidates
                if not _dataset_candidate_is_operator_specific(item)
            ]
            fallback_dataset = (
                generic_ranked[0] if generic_ranked else ranked_dataset_candidates[0]
            )
            dataset_options = [fallback_dataset]
            debug_payload["dataset_option_fallback"] = [
                str(fallback_dataset.get("dataset_id", "")).strip()
            ]
            debug_payload["dataset_option_fallback_source"] = "ranked_dataset_seed"
    debug_payload["dataset_options"] = dataset_options
    if not dataset_options:
        debug_payload["failure_stage"] = "rank_datasets"
        debug_payload["failure_reason"] = "no_dataset_options"
        return None, debug_payload
    (
        dataset_candidate,
        dataset_selection_debug,
    ) = await _select_benchmark_dataset_with_agent(
        agent=agent,
        task=task,
        dataset_options=dataset_options,
        benchmark_root=benchmark_root,
    )
    debug_payload["dataset_selection"] = dataset_selection_debug
    if dataset_candidate is None:
        dataset_candidate = dataset_options[0]
        debug_payload["dataset_selection_source"] = "default_first_option"
    else:
        debug_payload["dataset_selection_source"] = dataset_selection_debug.get(
            "selection_source"
        )
    selected_dataset_id = str(dataset_candidate.get("dataset_id", "")).strip()
    compatible_candidates = [
        item
        for item in candidates
        if _benchmark_operator_compatible_with_dataset(
            operator=item,
            dataset_candidate=dataset_candidate,
        )
    ]
    if not compatible_candidates:
        compatible_candidates = _select_benchmark_candidate_subset(
            task=task,
            candidates=candidates,
            benchmark_root=benchmark_root,
        )
        debug_payload["compatible_candidate_fallback"] = [
            str(item.get("name", "")).strip()
            for item in compatible_candidates
            if str(item.get("name", "")).strip()
        ]
    debug_payload["compatible_candidate_names"] = [
        str(item.get("name", "")).strip()
        for item in compatible_candidates
        if str(item.get("name", "")).strip()
    ]
    if not compatible_candidates:
        debug_payload["failure_stage"] = "filter_compatible_candidates"
        debug_payload["failure_reason"] = "no_compatible_candidates"
        return None, debug_payload
    prompt = _build_benchmark_register_selection_prompt(
        task=task,
        candidates=compatible_candidates,
        benchmark_root=benchmark_root,
        excluded_tools=excluded_tools,
        dataset_candidate=dataset_candidate,
    )
    timeout_seconds = _benchmark_register_agentic_selection_timeout_seconds()
    attempts: list[dict[str, object]] = []
    text = ""
    parsed: dict[str, object] | None = None
    for attempt_index in range(2):
        result, invoke_debug = await _invoke_benchmark_register_selector(
            selector=agent,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
        )
        if result is None:
            debug_payload["failure_stage"] = "tool_selection"
            debug_payload["failure_reason"] = "agent_invoke_failed"
            if invoke_debug.get("failure_reason") in {
                "direct_invoke_timeout",
                "fallback_invoke_timeout",
            }:
                debug_payload["failure_reason"] = "agent_invoke_timeout"
            if "timeout_seconds" in invoke_debug:
                debug_payload["timeout_seconds"] = invoke_debug["timeout_seconds"]
            debug_payload["selector_invocation"] = invoke_debug
            debug_payload["agent_attempts"] = attempts
            return None, debug_payload
        usage: dict[str, object] | None = None
        messages = result.get("messages", []) if isinstance(result, dict) else []
        if messages:
            refusal_message = _extract_messages_refusal(messages)
            if refusal_message is not None:
                return None
            text = _last_ai_text(messages)
            usage_metadata = getattr(messages[-1], "usage_metadata", None)
            if isinstance(usage_metadata, dict):
                usage = {str(k): v for k, v in usage_metadata.items()}
        else:
            refusal_message = _extract_model_refusal_message(result)
            if refusal_message is not None:
                return None
            text = _message_text(result)
            usage_metadata = getattr(result, "usage_metadata", None)
            if isinstance(usage_metadata, dict):
                usage = {str(k): v for k, v in usage_metadata.items()}
        attempt_details: dict[str, object] = {
            "attempt": attempt_index + 1,
            "raw_output": text,
            "usage": usage,
            "selector_invocation": invoke_debug,
        }
        parsed = _extract_generic_json_payload(text)
        attempt_details["parsed_payload_found"] = parsed is not None
        if parsed is None and text.strip():
            fallback_tools = _benchmark_selected_tools_from_text(
                text=text,
                candidates=compatible_candidates,
                excluded_tools=excluded_tools,
            )
            if fallback_tools:
                parsed = {
                    "selected_tools": fallback_tools,
                    "selection_rationale": "Recovered selected tools from non-JSON agent text.",
                }
                attempt_details["text_fallback_selected_tools"] = fallback_tools
        attempts.append(attempt_details)
        if parsed is not None:
            break
        if text.strip():
            break
    if parsed is None:
        debug_payload["failure_stage"] = "tool_selection"
        debug_payload["failure_reason"] = "agent_output_not_parseable"
        debug_payload["agent_attempts"] = attempts
        return None, debug_payload
    preferred_candidates = _select_benchmark_candidate_subset(
        task=task,
        candidates=compatible_candidates,
        benchmark_root=benchmark_root,
    )
    preferred_names = [
        str(item.get("name", "")).strip()
        for item in preferred_candidates
        if str(item.get("name", "")).strip()
    ]
    preferred_count = max(1, len(preferred_names))
    candidate_names = {
        str(item.get("name", "")).strip() for item in compatible_candidates
    }
    selected_tools = [
        str(item).strip()
        for item in parsed.get("selected_tools", [])
        if isinstance(item, str) and str(item).strip() in candidate_names
    ]
    selected_tools = [tool for tool in selected_tools if tool not in excluded_tools]
    if not selected_tools:
        debug_payload["failure_stage"] = "tool_selection"
        debug_payload["failure_reason"] = "no_valid_selected_tools"
        debug_payload["agent_attempts"] = attempts
        return None, debug_payload
    explicit_mentions = [
        name
        for name in preferred_names
        if _task_explicitly_mentions_benchmark_tool(task, name)
    ]
    if explicit_mentions:
        selected_tools = list(dict.fromkeys([*explicit_mentions, *selected_tools]))
    elif len(preferred_names) > 1 and set(selected_tools).issubset(
        set(preferred_names)
    ):
        selected_tools = preferred_names
    elif preferred_count <= 1:
        selected_tools = selected_tools[:1]
    else:
        selected_tools = selected_tools[:preferred_count]
    selected_operators = [
        item
        for item in compatible_candidates
        if str(item.get("name", "")).strip() in set(selected_tools)
    ]
    result = {
        "task": task,
        "dataset_key": selected_dataset_id or _benchmark_dataset_hint_from_task(task),
        "selection_strategy": "agent_operator_store_search",
        "selected_tools": selected_tools,
        "selected_operators": selected_operators,
        "requested_tools": [],
        "excluded_tools": sorted(excluded_tools),
        "allowed_tools": [str(item.get("name", "")) for item in compatible_candidates],
        "operator_store_roots": [
            str(path) for path in _candidate_operator_store_roots(workspace_root)
        ],
        "catalog_available": False,
        "candidate_count": len(compatible_candidates),
        "selected_dataset_id": selected_dataset_id,
        "dataset_candidates": dataset_options,
        "default_preferred_tools": preferred_names,
        "candidates": compatible_candidates,
        "agent_attempts": attempts,
        "agent_selection_rationale": str(parsed.get("selection_rationale", "")).strip(),
        "agent_raw_output": text,
    }
    result["selected_dataset"] = dataset_candidate
    debug_payload["result_preview"] = {
        "dataset_key": result["dataset_key"],
        "selected_tools": result["selected_tools"],
    }
    return result, debug_payload


async def _select_benchmark_tools_with_agent_exploratory(
    *,
    agent,
    task: str,
    workspace_root: Path,
    candidates: list[dict[str, object]],
    excluded_tools: set[str],
    benchmark_root: str,
    debug_payload: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    dataset_options = _rank_local_dataset_store_candidates(
        task=task,
        workspace_root=workspace_root,
        limit=12,
    )
    debug_payload["dataset_strategy"] = "per_operator_dataset"
    debug_payload["dataset_options"] = dataset_options
    prompt = _build_benchmark_register_exploratory_selection_prompt(
        task=task,
        candidates=candidates,
        dataset_options=dataset_options,
        benchmark_root=benchmark_root,
        excluded_tools=excluded_tools,
    )
    timeout_seconds = _benchmark_register_agentic_selection_timeout_seconds()
    result, invoke_debug = await _invoke_benchmark_register_selector(
        selector=agent,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
    )
    if result is None:
        debug_payload["failure_stage"] = "exploratory_selection"
        debug_payload["failure_reason"] = "agent_invoke_failed"
        if invoke_debug.get("failure_reason") in {
            "direct_invoke_timeout",
            "fallback_invoke_timeout",
        }:
            debug_payload["failure_reason"] = "agent_invoke_timeout"
        debug_payload["selector_invocation"] = invoke_debug
        return None, debug_payload

    messages = result.get("messages", []) if isinstance(result, dict) else []
    if messages:
        refusal_message = _extract_messages_refusal(messages)
        if refusal_message is not None:
            debug_payload["failure_stage"] = "exploratory_selection"
            debug_payload["failure_reason"] = "model_refusal"
            debug_payload["agent_attempts"] = [{"raw_output": refusal_message}]
            return None, debug_payload
        text = _last_ai_text(messages)
        usage_metadata = getattr(messages[-1], "usage_metadata", None)
    else:
        refusal_message = _extract_model_refusal_message(result)
        if refusal_message is not None:
            debug_payload["failure_stage"] = "exploratory_selection"
            debug_payload["failure_reason"] = "model_refusal"
            debug_payload["agent_attempts"] = [{"raw_output": refusal_message}]
            return None, debug_payload
        text = _message_text(result)
        usage_metadata = getattr(result, "usage_metadata", None)
    usage = (
        {str(k): v for k, v in usage_metadata.items()}
        if isinstance(usage_metadata, dict)
        else None
    )
    parsed = _extract_generic_json_payload(text)
    attempt = {
        "attempt": 1,
        "raw_output": text,
        "usage": usage,
        "selector_invocation": invoke_debug,
        "parsed_payload_found": parsed is not None,
    }
    if parsed is None and text.strip():
        fallback_tools = _benchmark_selected_tools_from_text(
            text=text,
            candidates=candidates,
            excluded_tools=excluded_tools,
        )
        if fallback_tools:
            parsed = {
                "selected_tools": fallback_tools,
                "selection_rationale": "Recovered selected tools from non-JSON agent text.",
            }
            attempt["text_fallback_selected_tools"] = fallback_tools
    debug_payload["agent_attempts"] = [attempt]
    if parsed is None:
        debug_payload["failure_stage"] = "exploratory_selection"
        debug_payload["failure_reason"] = "agent_output_not_parseable"
        return None, debug_payload

    preferred_candidates = _select_benchmark_candidate_subset(
        task=task,
        candidates=candidates,
        benchmark_root=benchmark_root,
    )
    preferred_names = [
        str(item.get("name", "")).strip()
        for item in preferred_candidates
        if str(item.get("name", "")).strip()
    ]
    candidate_names = {str(item.get("name", "")).strip() for item in candidates}
    selected_tools = [
        str(item).strip()
        for item in parsed.get("selected_tools", [])
        if isinstance(item, str)
        and str(item).strip() in candidate_names
        and str(item).strip() not in excluded_tools
    ]
    if not selected_tools:
        debug_payload["failure_stage"] = "exploratory_selection"
        debug_payload["failure_reason"] = "no_valid_selected_tools"
        return None, debug_payload
    explicit_mentions = [
        name
        for name in preferred_names
        if _task_explicitly_mentions_benchmark_tool(task, name)
    ]
    if explicit_mentions:
        selected_tools = list(dict.fromkeys([*explicit_mentions, *selected_tools]))
    elif len(preferred_names) > 1 and set(selected_tools).issubset(
        set(preferred_names)
    ):
        selected_tools = preferred_names
    elif len(preferred_names) <= 1:
        selected_tools = selected_tools[:1]
    else:
        selected_tools = selected_tools[: len(preferred_names)]

    selected_operators = [
        item
        for item in candidates
        if str(item.get("name", "")).strip() in set(selected_tools)
    ]
    raw_tool_dataset_keys = parsed.get("tool_dataset_keys")
    requested_dataset_keys = (
        {
            str(tool): str(dataset_id).strip()
            for tool, dataset_id in raw_tool_dataset_keys.items()
            if isinstance(tool, str) and str(dataset_id).strip()
        }
        if isinstance(raw_tool_dataset_keys, dict)
        else {}
    )
    tool_dataset_keys, selected_datasets = _resolve_benchmark_dataset_keys_for_tools(
        task=task,
        workspace_root=workspace_root,
        operator_candidates=selected_operators,
        selected_tools=selected_tools,
        excluded_tools=excluded_tools,
        benchmark_root=benchmark_root,
        requested_dataset_keys=requested_dataset_keys,
    )
    unique_dataset_keys = sorted({key for key in tool_dataset_keys.values() if key})
    result_payload = {
        "task": task,
        "dataset_key": unique_dataset_keys[0] if len(unique_dataset_keys) == 1 else "",
        "dataset_strategy": "per_operator_dataset",
        "selection_strategy": "agent_operator_store_exploratory_search",
        "selected_tools": selected_tools,
        "selected_operators": selected_operators,
        "requested_tools": [],
        "excluded_tools": sorted(excluded_tools),
        "allowed_tools": [str(item.get("name", "")) for item in candidates],
        "operator_store_roots": [
            str(path) for path in _candidate_operator_store_roots(workspace_root)
        ],
        "catalog_available": False,
        "candidate_count": len(candidates),
        "dataset_candidates": dataset_options,
        "tool_dataset_keys": tool_dataset_keys,
        "selected_datasets": selected_datasets,
        "default_preferred_tools": preferred_names,
        "candidates": candidates,
        "agent_attempts": [attempt],
        "agent_selection_rationale": str(parsed.get("selection_rationale", "")).strip(),
        "agent_raw_output": text,
    }
    if len(unique_dataset_keys) == 1 and selected_datasets:
        result_payload["selected_dataset_id"] = unique_dataset_keys[0]
        result_payload["selected_dataset"] = selected_datasets.get(
            unique_dataset_keys[0]
        )
    debug_payload["result_preview"] = {
        "dataset_strategy": "per_operator_dataset",
        "dataset_key": result_payload["dataset_key"],
        "tool_dataset_keys": tool_dataset_keys,
        "selected_tools": selected_tools,
    }
    return result_payload, debug_payload


def _resolve_benchmark_selected_tools(
    *,
    task: str,
    workspace_root: Path,
    benchmark_root: str,
    requested_tools: list[str],
    excluded_tools: set[str],
    selection_override: dict[str, object] | None = None,
) -> tuple[list[str], dict[str, object]]:
    candidate_pool = _collect_benchmark_operator_candidates(
        task=task,
        workspace_root=workspace_root,
        excluded_tools=excluded_tools,
        limit=_BENCHMARK_REGISTER_AGENTIC_CANDIDATE_LIMIT,
    )
    dataset_strategy = _benchmark_dataset_strategy_for_task(task)
    dataset_candidate = (
        _resolve_benchmark_dataset_candidate(
            task=task,
            workspace_root=workspace_root,
            operator_candidates=candidate_pool,
            requested_tools=requested_tools,
            excluded_tools=excluded_tools,
            benchmark_root=benchmark_root,
        )
        if dataset_strategy == "shared_dataset"
        else None
    )
    dataset_key = (
        str(dataset_candidate.get("dataset_id", "")).strip()
        if dataset_candidate
        else ""
    )
    if dataset_candidate is not None:
        candidate_pool = [
            item
            for item in candidate_pool
            if _benchmark_operator_compatible_with_dataset(
                operator=item,
                dataset_candidate=dataset_candidate,
            )
        ]
    if selection_override is not None:
        selected_tools = [
            str(item)
            for item in selection_override.get("selected_tools", [])
            if isinstance(item, str) and item.strip() and item not in excluded_tools
        ]
        report = dict(selection_override)
        report["selected_tools"] = selected_tools
        report["benchmark_root"] = benchmark_root
        report["excluded_tools"] = sorted(excluded_tools)
        report.setdefault("task", task)
        report.setdefault("dataset_strategy", dataset_strategy)
        if (
            report.get("dataset_strategy") == "shared_dataset"
            and not str(report.get("dataset_key", "")).strip()
        ):
            report["dataset_key"] = dataset_key or _benchmark_dataset_hint_from_task(
                task
            )
        if dataset_candidate is not None and not isinstance(
            report.get("selected_dataset"), dict
        ):
            report["selected_dataset"] = dataset_candidate
        if report.get("dataset_strategy") == "per_operator_dataset":
            raw_map = report.get("tool_dataset_keys")
            existing_map = (
                {
                    str(tool): str(dataset_id).strip()
                    for tool, dataset_id in raw_map.items()
                    if isinstance(tool, str) and str(dataset_id).strip()
                }
                if isinstance(raw_map, dict)
                else {}
            )
            if not existing_map:
                tool_dataset_keys, selected_datasets = (
                    _resolve_benchmark_dataset_keys_for_tools(
                        task=task,
                        workspace_root=workspace_root,
                        operator_candidates=candidate_pool,
                        selected_tools=selected_tools,
                        excluded_tools=excluded_tools,
                        benchmark_root=benchmark_root,
                    )
                )
                report["tool_dataset_keys"] = tool_dataset_keys
                report["selected_datasets"] = selected_datasets
                unique_dataset_keys = sorted(
                    {key for key in tool_dataset_keys.values() if key}
                )
                if (
                    len(unique_dataset_keys) == 1
                    and not str(report.get("dataset_key", "")).strip()
                ):
                    report["dataset_key"] = unique_dataset_keys[0]
        report.setdefault("selection_strategy", "agent_operator_store_search")
        report.setdefault("requested_tools", requested_tools)
        report.setdefault(
            "operator_store_roots",
            [str(path) for path in _candidate_operator_store_roots(workspace_root)],
        )
        report.setdefault("catalog_available", False)
        if not isinstance(report.get("selected_operators"), list) or not report.get(
            "selected_operators"
        ):
            selected_names = set(selected_tools)
            report["selected_operators"] = [
                item
                for item in candidate_pool
                if str(item.get("name", "")).strip() in selected_names
            ]
        return selected_tools, report
    if requested_tools:
        selected_tools = [
            tool for tool in requested_tools if tool not in excluded_tools
        ]
        selected_names = set(selected_tools)
        selected_operator_payloads = [
            item
            for item in candidate_pool
            if str(item.get("name", "")).strip() in selected_names
        ]
        final_strategy = "metadata_selected_tools"
    else:
        selected_operator_payloads = _select_benchmark_candidate_subset(
            task=task,
            candidates=candidate_pool,
            benchmark_root=benchmark_root,
        )
        selected_tools = [
            str(item.get("name", "")).strip()
            for item in selected_operator_payloads
            if str(item.get("name", "")).strip()
        ]
        if selected_tools:
            final_strategy = "operator_store_search"
        else:
            final_strategy = "operator_store_search_no_match"
    report = {
        "task": task,
        "benchmark_root": benchmark_root,
        "dataset_key": dataset_key or _benchmark_dataset_hint_from_task(task),
        "selected_dataset_id": dataset_key if dataset_candidate is not None else "",
        "dataset_strategy": dataset_strategy,
        "selection_strategy": final_strategy,
        "requested_tools": requested_tools,
        "excluded_tools": sorted(excluded_tools),
        "selected_tools": selected_tools,
        "selected_operators": selected_operator_payloads,
        "operator_store_roots": [
            str(path) for path in _candidate_operator_store_roots(workspace_root)
        ],
        "catalog_available": False,
    }
    if dataset_candidate is not None:
        report["selected_dataset"] = dataset_candidate
    if dataset_strategy == "per_operator_dataset" and selected_tools:
        tool_dataset_keys, selected_datasets = (
            _resolve_benchmark_dataset_keys_for_tools(
                task=task,
                workspace_root=workspace_root,
                operator_candidates=selected_operator_payloads,
                selected_tools=selected_tools,
                excluded_tools=excluded_tools,
                benchmark_root=benchmark_root,
            )
        )
        report["tool_dataset_keys"] = tool_dataset_keys
        report["selected_datasets"] = selected_datasets
        unique_dataset_keys = sorted({key for key in tool_dataset_keys.values() if key})
        if len(unique_dataset_keys) == 1:
            report["dataset_key"] = unique_dataset_keys[0]
    return selected_tools, report


def _collect_benchmark_operator_candidates(
    *,
    task: str,
    workspace_root: Path,
    excluded_tools: set[str],
    limit: int,
) -> list[dict[str, object]]:
    query = _benchmark_operator_query(task=task)
    candidates: dict[str, tuple[int, int, dict[str, object]]] = {}
    search_limit = max(limit * 2, 24)
    for store_root in _candidate_operator_store_roots(workspace_root):
        try:
            store = OperatorStore(store_root)
            rows = store.search_operators(
                OperatorSearchFilter(query=query, limit=search_limit)
            )
        except sqlite3.Error:
            continue
        query_matched = bool(rows)
        if not rows:
            try:
                rows = store.search_operators(OperatorSearchFilter(limit=search_limit))
            except sqlite3.Error:
                continue
        for rank, row in enumerate(rows):
            candidate = _benchmark_candidate_from_search_row(
                row=row,
                excluded_tools=excluded_tools,
            )
            if candidate is None:
                continue
            score = int(candidate.pop("_score"))
            name = str(candidate.get("name", "")).strip()
            overlap_score = _benchmark_query_overlap_score(
                query=query,
                searchable_text="\n".join(
                    [
                        name,
                        str(candidate.get("summary", "")),
                        str(candidate.get("canonical_text", "")),
                    ]
                ),
            )
            score += 4 * overlap_score
            score += _benchmark_intent_hint_score(
                query=query,
                searchable_text="\n".join(
                    [
                        name,
                        str(candidate.get("summary", "")),
                        str(candidate.get("canonical_text", "")),
                    ]
                ),
            )
            if not query_matched:
                score += overlap_score
            current = candidates.get(name)
            candidate["score"] = score
            candidate["rank"] = rank
            if (
                current is None
                or score > current[0]
                or (score == current[0] and rank < current[1])
            ):
                candidates[name] = (score, rank, candidate)
    for candidate in _rank_benchmark_operator_records_locally(
        workspace_root=workspace_root,
        excluded_tools=excluded_tools,
        query=query,
    ):
        name = str(candidate.get("name", "")).strip()
        if not name:
            continue
        score = int(candidate.get("score", 0))
        rank = int(candidate.get("rank", 0))
        current = candidates.get(name)
        if (
            current is None
            or score > current[0]
            or (score == current[0] and rank < current[1])
        ):
            candidates[name] = (score, rank, candidate)
    for candidate in _collect_explicit_benchmark_operator_candidates(
        task=task,
        workspace_root=workspace_root,
        excluded_tools=excluded_tools,
    ):
        name = str(candidate.get("name", "")).strip()
        if not name:
            continue
        score = int(candidate.get("score", 0)) + 100
        rank = int(candidate.get("rank", 0))
        candidate["score"] = score
        current = candidates.get(name)
        if (
            current is None
            or score > current[0]
            or (score == current[0] and rank < current[1])
        ):
            candidates[name] = (score, rank, candidate)
    ranked = sorted(
        candidates.values(),
        key=lambda item: (-item[0], item[1], str(item[2].get("name", "")).casefold()),
    )
    ranked_candidates = [item[2] for item in ranked]
    explicitly_named = [
        candidate
        for candidate in ranked_candidates
        if _task_explicitly_mentions_benchmark_tool(
            task,
            str(candidate.get("name", "")).strip(),
        )
    ]
    if explicitly_named:
        explicit_names = {
            str(candidate.get("name", "")).strip() for candidate in explicitly_named
        }
        target_count = max(1, limit, len(explicitly_named))
        merged = explicitly_named + [
            candidate
            for candidate in ranked_candidates
            if str(candidate.get("name", "")).strip() not in explicit_names
        ]
        return merged[:target_count]
    return ranked_candidates[: max(1, limit)]


def _collect_explicit_benchmark_operator_candidates(
    *,
    task: str,
    workspace_root: Path,
    excluded_tools: set[str],
) -> list[dict[str, object]]:
    candidates: dict[str, dict[str, object]] = {}
    for store_root in _candidate_operator_store_roots(workspace_root):
        for operator_path in sorted(store_root.glob("operators/*/operator.json")):
            try:
                payload = json.loads(operator_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidate = _benchmark_candidate_from_operator_payload(
                payload=payload,
                operator_path=operator_path,
                excluded_tools=excluded_tools,
            )
            if candidate is None:
                continue
            name = str(candidate.get("name", "")).strip()
            if not name or not _task_explicitly_mentions_benchmark_tool(task, name):
                continue
            current = candidates.get(name)
            if current is None or int(candidate.get("_score", 0)) > int(
                current.get("_score", 0)
            ):
                candidate["rank"] = -100
                candidates[name] = candidate
    return list(candidates.values())


def _search_operator_store_for_benchmark_tools(
    *,
    task: str,
    workspace_root: Path,
    excluded_tools: set[str],
    benchmark_root: str = "",
) -> list[str]:
    candidates = _collect_benchmark_operator_candidates(
        task=task,
        workspace_root=workspace_root,
        excluded_tools=excluded_tools,
        limit=_BENCHMARK_REGISTER_AGENTIC_CANDIDATE_LIMIT,
    )
    return [
        str(item.get("name", "")).strip()
        for item in _select_benchmark_candidate_subset(
            task=task,
            candidates=candidates,
            benchmark_root=benchmark_root,
        )
        if str(item.get("name", "")).strip()
    ]


def _benchmark_operator_query(*, task: str) -> str:
    return task.strip()


def _candidate_operator_store_roots(workspace_root: Path) -> list[Path]:
    return _discover_shared_store_roots(
        workspace_root=workspace_root,
        store_dirname="operator_store",
        shared_root_env=_SHARED_OPERATOR_STORE_ROOT_ENV,
    )


def _candidate_dataset_store_roots(workspace_root: Path) -> list[Path]:
    return _discover_shared_store_roots(
        workspace_root=workspace_root,
        store_dirname="dataset_store",
        shared_root_env=_SHARED_DATASET_STORE_ROOT_ENV,
    )


def _benchmark_dataset_hint_from_task(task: str) -> str:
    matches = re.findall(r"\b[a-z0-9]+(?:[-_][a-z0-9]+){2,}\b", task.casefold())
    return matches[0] if matches else ""


def _benchmark_dataset_strategy_for_task(task: str) -> str:
    return (
        "shared_dataset"
        if _benchmark_task_requires_shared_dataset(task)
        else "per_operator_dataset"
    )


def _benchmark_task_requires_shared_dataset(task: str) -> bool:
    if _benchmark_dataset_hint_from_task(task):
        return True
    normalized = task.casefold()
    relaxed_markers = (
        "不要求同一",
        "不需要同一",
        "不用同一",
        "无需同一",
        "不要求共享",
        "不需要共享",
        "分别给",
        "分别使用",
        "不同数据集",
        "separate datasets",
        "different datasets",
    )
    if any(marker in normalized for marker in relaxed_markers):
        return False
    if "共享" in normalized and "数据" in normalized:
        return True
    shared_markers = (
        "同一份",
        "同一个数据",
        "相同数据",
        "共享数据",
        "统一数据",
        "公平比较",
        "可公平比较",
        "same dataset",
        "same input",
        "same reads",
        "same fastq",
        "shared dataset",
        "fair comparison",
    )
    return any(marker in normalized for marker in shared_markers)


def _resolve_benchmark_dataset_keys_for_tools(
    *,
    task: str,
    workspace_root: Path,
    operator_candidates: list[dict[str, object]],
    selected_tools: list[str],
    excluded_tools: set[str],
    benchmark_root: str,
    requested_dataset_keys: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    requested_dataset_keys = requested_dataset_keys or {}
    operator_by_name = {
        str(candidate.get("name", "")).strip(): candidate
        for candidate in operator_candidates
        if str(candidate.get("name", "")).strip()
    }
    resolved: dict[str, str] = {}
    selected_datasets: dict[str, dict[str, object]] = {}
    for tool in selected_tools:
        operator = operator_by_name.get(tool)
        if operator is None:
            continue
        requested_key = requested_dataset_keys.get(tool, "").strip()
        dataset_candidate = (
            _find_benchmark_dataset_candidate_by_id(
                workspace_root=workspace_root,
                dataset_id=requested_key,
            )
            if requested_key
            else None
        )
        if (
            dataset_candidate is not None
            and not _benchmark_operator_compatible_with_dataset(
                operator=operator,
                dataset_candidate=dataset_candidate,
            )
        ):
            dataset_candidate = None
        if dataset_candidate is None:
            dataset_candidate = _resolve_benchmark_dataset_candidate(
                task=task,
                workspace_root=workspace_root,
                operator_candidates=[operator],
                requested_tools=[tool],
                excluded_tools=excluded_tools,
                benchmark_root=benchmark_root,
            )
        if dataset_candidate is None:
            continue
        dataset_id = str(dataset_candidate.get("dataset_id", "")).strip()
        if not dataset_id:
            continue
        resolved[tool] = dataset_id
        selected_datasets[dataset_id] = dataset_candidate
    return resolved, selected_datasets


def _find_benchmark_dataset_candidate_by_id(
    *,
    workspace_root: Path,
    dataset_id: str,
) -> dict[str, object] | None:
    dataset_id = dataset_id.strip()
    if not dataset_id:
        return None
    for candidate in _benchmark_user_dataset_candidates(
        task=dataset_id,
        workspace_root=workspace_root,
    ):
        if str(candidate.get("dataset_id", "")).strip() == dataset_id:
            return candidate
    for store_root in _candidate_dataset_store_roots(workspace_root):
        try:
            store = DatasetStore(store_root)
            rows = store.search_datasets(
                DatasetSearchFilter(dataset_id=dataset_id, limit=3)
            )
        except sqlite3.Error:
            continue
        for row in rows:
            if str(row.get("dataset_id", "")).strip() == dataset_id:
                return _local_dataset_candidate_from_search_row(row)
    return None


def _resolve_benchmark_dataset_candidate(
    *,
    task: str,
    workspace_root: Path,
    operator_candidates: list[dict[str, object]],
    requested_tools: list[str],
    excluded_tools: set[str],
    benchmark_root: str = "",
) -> dict[str, object] | None:
    explicit_dataset_key = _benchmark_dataset_hint_from_task(task)
    ranked_datasets = _rank_local_dataset_store_candidates(
        task=task,
        workspace_root=workspace_root,
        limit=12,
    )
    if explicit_dataset_key:
        for candidate in ranked_datasets:
            if str(candidate.get("dataset_id", "")).strip() == explicit_dataset_key:
                return candidate
        for store_root in _candidate_dataset_store_roots(workspace_root):
            try:
                store = DatasetStore(store_root)
                rows = store.search_datasets(
                    DatasetSearchFilter(dataset_id=explicit_dataset_key, limit=3)
                )
            except sqlite3.Error:
                continue
            for row in rows:
                if str(row.get("dataset_id", "")).strip() == explicit_dataset_key:
                    return _local_dataset_candidate_from_search_row(row)

    target_names = {
        tool for tool in requested_tools if tool.strip() and tool not in excluded_tools
    }
    if target_names:
        relevant_operators = [
            candidate
            for candidate in operator_candidates
            if str(candidate.get("name", "")).strip() in target_names
        ]
    else:
        relevant_operators = _select_benchmark_candidate_subset(
            task=task,
            candidates=operator_candidates,
            benchmark_root=benchmark_root,
        )
    if not relevant_operators:
        relevant_operators = operator_candidates
    if not ranked_datasets or not relevant_operators:
        return None

    def score(dataset_candidate: dict[str, object]) -> tuple[int, int, int, str]:
        compatible = [
            candidate
            for candidate in relevant_operators
            if _benchmark_operator_compatible_with_dataset(
                operator=candidate,
                dataset_candidate=dataset_candidate,
            )
        ]
        compatibility_count = len(compatible)
        shared_candidate = (
            1
            if compatibility_count >= 2
            or compatibility_count == len(relevant_operators)
            else 0
        )
        generic_bonus = (
            0 if _dataset_candidate_is_operator_specific(dataset_candidate) else 1
        )
        query_score = _benchmark_dataset_task_score(
            task=task, dataset_candidate=dataset_candidate
        )
        return (
            compatibility_count,
            shared_candidate,
            query_score + generic_bonus,
            str(dataset_candidate.get("dataset_id", "")),
        )

    ranked = sorted(
        ranked_datasets,
        key=score,
        reverse=True,
    )
    multi_tool_benchmark = len(
        relevant_operators
    ) >= 2 or _task_requests_multiple_benchmark_tools(task)
    if multi_tool_benchmark:
        generic_ranked = [
            candidate
            for candidate in ranked
            if not _dataset_candidate_is_operator_specific(candidate)
            and score(candidate)[0] > 0
        ]
        if generic_ranked:
            return generic_ranked[0]
    best = ranked[0]
    return best if score(best)[0] > 0 else None


def _dataset_candidate_is_operator_specific(
    dataset_candidate: dict[str, object],
) -> bool:
    compatible_ids = [
        str(item).strip()
        for item in dataset_candidate.get("compatible_operator_ids", [])
        if isinstance(item, str) and str(item).strip()
    ]
    return bool(compatible_ids)


def _benchmark_operator_compatible_with_dataset(
    *,
    operator: dict[str, object],
    dataset_candidate: dict[str, object],
) -> bool:
    operator_id = str(operator.get("operator_id", "")).strip()
    compatible_ids = {
        str(item).strip()
        for item in dataset_candidate.get("compatible_operator_ids", [])
        if isinstance(item, str) and str(item).strip()
    }
    if compatible_ids:
        return operator_id in compatible_ids

    dataset_files = dataset_candidate.get("files")
    if not isinstance(dataset_files, list) or not dataset_files:
        return False
    dataset_media_counts: dict[str, int] = {}
    for item in dataset_files:
        if not isinstance(item, dict):
            continue
        media = _normalize_benchmark_media_type(str(item.get("media_type", "")).strip())
        if not media or media == "json":
            continue
        dataset_media_counts[media] = dataset_media_counts.get(media, 0) + 1
    if not dataset_media_counts:
        return False

    operator_inputs = operator.get("inputs")
    input_rows = (
        [item for item in operator_inputs if isinstance(item, dict)]
        if isinstance(operator_inputs, list)
        else []
    )
    required_media: dict[str, int] = {}
    input_media_types = operator.get("input_media_types")
    if isinstance(input_media_types, list):
        for item in input_media_types:
            media = _normalize_benchmark_media_type(str(item).strip())
            if not media or media == "json":
                continue
            required_media[media] = max(required_media.get(media, 0), 1)
    if _operator_looks_paired_end_read_workload(
        inputs=input_rows,
        inputs_json_path=str(operator.get("inputs_json_path", "")).strip(),
    ):
        required_media.pop("fasta", None)
        required_media["fastq"] = max(required_media.get("fastq", 0), 2)
    if _operator_inputs_look_receptor_ligand(input_rows):
        required_media["pdbqt"] = max(required_media.get("pdbqt", 0), 2)
    if not required_media:
        unique_paths_by_media: dict[str, set[str]] = {}
        for item in input_rows:
            media = _normalize_benchmark_media_type(
                str(item.get("media_type", "")).strip()
            )
            if not media or media == "json":
                continue
            path_key = (
                str(item.get("path", "")).strip() or str(item.get("name", "")).strip()
            )
            if path_key:
                unique_paths_by_media.setdefault(media, set()).add(path_key)
        required_media = {
            media: len(paths) for media, paths in unique_paths_by_media.items() if paths
        }
    if not required_media:
        return False
    return all(
        dataset_media_counts.get(media, 0) >= count
        for media, count in required_media.items()
    )


def _operator_inputs_look_paired_end(inputs: list[dict[str, object]]) -> bool:
    names = {
        re.sub(r"[^a-z0-9]+", "", str(item.get("name", "")).casefold())
        for item in inputs
        if isinstance(item, dict)
    }
    has_first = any(name in names for name in {"read1", "r1", "fastq1", "fq1"})
    has_second = any(name in names for name in {"read2", "r2", "fastq2", "fq2"})
    return has_first and has_second


def _operator_looks_paired_end_read_workload(
    *,
    inputs: list[dict[str, object]],
    inputs_json_path: str,
) -> bool:
    return _operator_inputs_look_paired_end(inputs) or _inputs_json_looks_paired_end(
        inputs_json_path
    )


@lru_cache(maxsize=256)
def _inputs_json_looks_paired_end(inputs_json_path: str) -> bool:
    path_str = inputs_json_path.strip()
    if not path_str:
        return False
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    names = {
        re.sub(r"[^a-z0-9]+", "", str(key).casefold().split(".")[-1])
        for key in payload
        if isinstance(key, str) and str(key).strip()
    }
    has_first = any(name in names for name in {"read1", "r1", "fastq1", "fq1"})
    has_second = any(name in names for name in {"read2", "r2", "fastq2", "fq2"})
    return has_first and has_second


def _operator_inputs_look_receptor_ligand(inputs: list[dict[str, object]]) -> bool:
    names = {
        re.sub(r"[^a-z0-9]+", "", str(item.get("name", "")).casefold())
        for item in inputs
        if isinstance(item, dict)
    }
    return any("receptor" in name for name in names) and any(
        "ligand" in name for name in names
    )


def _normalize_benchmark_media_type(value: str) -> str:
    lowered = value.casefold().strip()
    if not lowered:
        return ""
    if "fastq" in lowered or lowered in {"fq", "reads"}:
        return "fastq"
    if "fasta" in lowered or lowered in {"fa", "fna"}:
        return "fasta"
    if "json" in lowered:
        return "json"
    if "gtf" in lowered:
        return "gtf"
    if "pdbqt" in lowered:
        return "pdbqt"
    if "pdb" in lowered:
        return "pdb"
    return lowered


def _benchmark_media_type_from_path(path: Path) -> str:
    name = path.name.casefold()
    if name.endswith((".fastq.gz", ".fq.gz", ".fastq", ".fq")):
        return "fastq"
    if name.endswith((".fasta.gz", ".fa.gz", ".fna.gz", ".fasta", ".fa", ".fna")):
        return "fasta"
    if name.endswith(".gtf"):
        return "gtf"
    if name.endswith(".pdbqt"):
        return "pdbqt"
    if name.endswith(".pdb"):
        return "pdb"
    if name.endswith(".json"):
        return "json"
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".tsv"):
        return "tsv"
    return ""


def _benchmark_data_file_role(path: Path, *, media_type: str) -> str:
    name = path.name.casefold()
    if media_type == "fastq":
        if re.search(r"(^|[_\-.])(?:r?1|read1)(?=[_\-.])", name):
            return "read1"
        if re.search(r"(^|[_\-.])(?:r?2|read2)(?=[_\-.])", name):
            return "read2"
        if "pacbio" in name:
            return "pacbio"
        return "reads_fastq"
    if media_type == "fasta":
        if any(marker in name for marker in ("ref", "reference", "genome")):
            return "reference_fasta"
        return "reads_fasta"
    if media_type == "gtf":
        return "reference_gtf"
    return media_type


def _benchmark_task_path_candidates(task: str, *, workspace_root: Path) -> list[Path]:
    raw_values: list[str] = []
    raw_values.extend(re.findall(r"`([^`]+)`", task))
    raw_values.extend(
        re.findall(
            r"(?<![\w])(?:/[^\s`\"'，。；;）)]+|(?:workspace|experiments|data|datasets)/[^\s`\"'，。；;）)]+)",
            task,
        )
    )
    paths: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_values:
        cleaned = raw.strip().strip("`'\"“”‘’<>[]{}")
        cleaned = cleaned.rstrip(".,，。;；:)）")
        if not cleaned:
            continue
        raw_path = Path(cleaned)
        candidates = (
            [raw_path]
            if raw_path.is_absolute()
            else [
                workspace_root / raw_path,
                _PROJECT_ROOT / raw_path,
                Path.cwd() / raw_path,
            ]
        )
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(resolved)
            break
    return paths


def _benchmark_data_files_from_path(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if _benchmark_media_type_from_path(path) else []
    if not path.is_dir():
        return []

    def data_files(candidates: list[Path]) -> list[Path]:
        return [
            candidate
            for candidate in sorted(candidates)
            if candidate.is_file() and _benchmark_media_type_from_path(candidate)
        ]

    immediate = data_files(list(path.iterdir()))
    if immediate:
        return immediate[:64]
    nested = data_files(list(path.glob("*/*")))
    return nested[:64]


def _benchmark_user_dataset_candidate_from_path(path: Path) -> dict[str, object] | None:
    files = _benchmark_data_files_from_path(path)
    files = [
        item for item in files if _benchmark_media_type_from_path(item) != "json"
    ] or files
    if not files:
        return None
    dataset_root = path if path.is_dir() else path.parent
    try:
        resolved_root = dataset_root.resolve()
    except OSError:
        resolved_root = dataset_root
    slug = re.sub(r"[^a-z0-9]+", "-", resolved_root.name.casefold()).strip("-")
    digest = hashlib.sha1(str(resolved_root).encode("utf-8")).hexdigest()[:8]
    dataset_id = f"external-{slug or 'dataset'}-{digest}"
    file_records: list[dict[str, object]] = []
    media_types: set[str] = set()
    for file_path in files:
        media_type = _benchmark_media_type_from_path(file_path)
        if not media_type:
            continue
        media_types.add(media_type)
        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = None
        file_records.append(
            {
                "name": file_path.name,
                "role": _benchmark_data_file_role(file_path, media_type=media_type),
                "media_type": media_type,
                "uri": str(file_path),
                "sha256": "",
                "size_bytes": size_bytes,
            }
        )
    if not file_records:
        return None
    domain = "genome_assembly" if {"fastq", "fasta"} & media_types else "local_dataset"
    summary = (
        "User-provided external benchmark dataset discovered from the task text. "
        f"Root: {resolved_root}"
    )
    canonical_text = "\n".join(
        [
            f"dataset_id: {dataset_id}",
            f"name: user provided {resolved_root.name}",
            f"domain: {domain}",
            summary,
            "files: "
            + " ".join(
                f"{item['name']} {item['media_type']} {item['uri']}"
                for item in file_records
            ),
        ]
    )
    return {
        "dataset_id": dataset_id,
        "name": f"user provided {resolved_root.name}",
        "version": "user-provided",
        "domain": domain,
        "summary": summary,
        "canonical_text": canonical_text,
        "files": file_records,
        "tags": ["benchmark", "user-provided", "external", domain],
        "compatible_operator_ids": [],
        "record_path": "",
        "source_kind": "user_provided_external_path",
        "dataset_root": str(resolved_root),
    }


def _benchmark_user_dataset_candidates(
    *,
    task: str,
    workspace_root: Path,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in _benchmark_task_path_candidates(task, workspace_root=workspace_root):
        candidate = _benchmark_user_dataset_candidate_from_path(path)
        if candidate is None:
            continue
        dataset_id = str(candidate.get("dataset_id", "")).strip()
        if not dataset_id or dataset_id in seen:
            continue
        seen.add(dataset_id)
        candidates.append(candidate)
    return candidates


def _benchmark_dataset_task_score(
    *, task: str, dataset_candidate: dict[str, object]
) -> int:
    dataset_text = "\n".join(
        [
            str(dataset_candidate.get("dataset_id", "")),
            str(dataset_candidate.get("name", "")),
            str(dataset_candidate.get("summary", "")),
            str(dataset_candidate.get("domain", "")),
            str(dataset_candidate.get("canonical_text", "")),
        ]
    )
    score = _benchmark_query_overlap_score(query=task, searchable_text=dataset_text)
    score += _benchmark_intent_hint_score(query=task, searchable_text=dataset_text)
    if (
        str(dataset_candidate.get("source_kind", "")).strip()
        == "user_provided_external_path"
    ):
        score += 1000
        task_lower_for_source = task.casefold()
        if any(
            marker in task_lower_for_source
            for marker in (
                "不要使用 dataset_store",
                "不用 dataset_store",
                "不使用 dataset_store",
                "临时提供",
                "新数据目录",
                "new data",
                "external dataset",
                "provided dataset",
            )
        ):
            score += 300

    task_lower = task.casefold()
    dataset_lower = dataset_text.casefold()
    domain = str(dataset_candidate.get("domain", "")).strip().casefold()

    wants_assembly = any(marker in task_lower for marker in ("assembly", "组装"))
    wants_long_read = any(
        marker in task_lower
        for marker in ("long read", "长读", "pacbio", "hifi", "ont", "nanopore")
    )
    wants_short_read = any(
        marker in task_lower
        for marker in ("short read", "短读", "paired-end", "paired end")
    )
    wants_circrna = any(
        marker in task_lower for marker in ("circrna", "circ", "环状rna")
    )
    wants_immune_escape = any(
        marker in task_lower for marker in ("immune", "escape", "免疫逃逸")
    )

    if wants_assembly:
        if (
            domain == "genome_assembly"
            or "assembly" in dataset_lower
            or "组装" in dataset_lower
        ):
            score += 20
        else:
            score -= 20
    if wants_long_read:
        if any(
            marker in dataset_lower
            for marker in (
                "long-read",
                "long read",
                "长读",
                "pacbio",
                "hifi",
                "ont",
                "nanopore",
            )
        ):
            score += 24
        else:
            score -= 12
    if wants_short_read:
        if any(
            marker in dataset_lower
            for marker in ("short-read", "short read", "短读", "paired")
        ):
            score += 16
    if wants_circrna:
        if "circrna" in domain or any(
            marker in dataset_lower for marker in ("circrna", "circ", "环状rna")
        ):
            score += 20
        else:
            score -= 10
    if wants_immune_escape:
        if any(
            marker in dataset_lower
            for marker in ("immune", "escape", "免疫逃逸", "covabdab", "pdbqt")
        ):
            score += 20
        else:
            score -= 10
    return score


def _candidate_benchmark_result_store_roots(workspace_root: Path) -> list[Path]:
    return _discover_shared_store_roots(
        workspace_root=workspace_root,
        store_dirname=_BENCHMARK_COMPARISON_HISTORY_STORE_DIR,
        shared_root_env=_SHARED_BENCHMARK_COMPARISON_HISTORY_STORE_ROOT_ENV,
    )


def _discover_shared_store_roots(
    *,
    workspace_root: Path,
    store_dirname: str,
    shared_root_env: str,
) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | None) -> None:
        if path is None or not path.exists() or not path.is_dir():
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    def sort_key(path: Path) -> tuple[int, str]:
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        return (-mtime, path.as_posix())

    add(workspace_root / store_dirname)
    shared_root = (get_env(shared_root_env, "") or "").strip()
    if shared_root:
        add(Path(shared_root))

    shared_workspace_root = _PROJECT_ROOT / "workspace"
    try:
        workspace_in_repo = workspace_root.resolve().is_relative_to(
            shared_workspace_root.resolve()
        )
    except OSError:
        workspace_in_repo = False
    except RuntimeError:
        workspace_in_repo = False
    if workspace_in_repo:
        add(shared_workspace_root / store_dirname)
    if (
        workspace_in_repo
        and shared_workspace_root.exists()
        and shared_workspace_root.is_dir()
    ):
        session_roots = sorted(
            (
                candidate
                for candidate in shared_workspace_root.glob(f"*/{store_dirname}")
                if candidate.is_dir()
            ),
            key=sort_key,
        )
        for candidate in session_roots:
            add(candidate)
    return roots


def _benchmark_candidate_from_search_row(
    *,
    row: dict[str, object],
    excluded_tools: set[str],
) -> dict[str, object] | None:
    operator_path_raw = row.get("operator_path")
    if not isinstance(operator_path_raw, str) or not operator_path_raw.strip():
        return None
    operator_path = Path(operator_path_raw)
    if not operator_path.exists():
        return None
    try:
        payload = json.loads(operator_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _benchmark_candidate_from_operator_payload(
        payload=payload,
        operator_path=operator_path,
        excluded_tools=excluded_tools,
    )


def _benchmark_candidate_from_operator_payload(
    *,
    payload: dict[str, object],
    operator_path: Path,
    excluded_tools: set[str],
) -> dict[str, object] | None:
    name = str(payload.get("name", "")).strip()
    if not name or name in excluded_tools:
        return None
    family = str(payload.get("family", "")).strip()
    tags = [
        str(tag).strip()
        for tag in payload.get("tags", [])
        if isinstance(tag, str) and tag.strip()
    ]
    validation_payload = payload.get("validation")
    validation_status = (
        validation_payload.get("status") if isinstance(validation_payload, dict) else ""
    )
    status = str(
        payload.get("validation_status")
        or payload.get("status")
        or validation_status
        or ""
    ).strip()
    if not status:
        tag_set = set(tags)
        if "registered_ready" in tag_set or "execution-ready" in tag_set:
            status = "registered_ready"
        elif "completed" in tag_set:
            status = "completed"
        elif "registered" in tag_set:
            status = "registered"
    if family not in {"benchmark", "github2workspace"}:
        return None
    partial_but_wdl_ready = status == "partial" and (
        "wdl-completed" in tags or "execution-ready" in tags
    )
    if (
        status not in {"completed", "registered_ready", "registered"}
        and not partial_but_wdl_ready
    ):
        return None
    score = 0
    if family == "benchmark":
        score += 20
    if status == "completed":
        score += 10
    elif status == "registered_ready":
        score += 6
    elif status == "registered":
        score += 3
    elif partial_but_wdl_ready:
        score += 1
    if "execution-ready" in tags or "wdl-completed" in tags:
        score += 2
    input_media_types = [
        str(item).strip()
        for item in payload.get("input_media_types", [])
        if isinstance(item, str) and item.strip()
    ]
    inputs_json_path = str(
        (payload.get("runtime") or {}).get("inputs_json_path", "")
        if isinstance(payload.get("runtime"), dict)
        else ""
    ).strip()
    input_rows = [item for item in payload.get("inputs", []) if isinstance(item, dict)]
    if _operator_looks_paired_end_read_workload(
        inputs=input_rows,
        inputs_json_path=inputs_json_path,
    ):
        normalized_input_media_types = [
            media
            for media in (
                _normalize_benchmark_media_type(item) for item in input_media_types
            )
            if media and media != "json" and media != "fasta"
        ]
        input_media_types = sorted({"fastq", *normalized_input_media_types, "json"})
    return {
        "name": name,
        "operator_id": str(payload.get("operator_id", "")).strip(),
        "family": family,
        "validation_status": status,
        "summary": str(payload.get("summary", "")),
        "canonical_text": str(payload.get("canonical_text", "")),
        "input_media_types": input_media_types,
        "output_media_types": [
            str(item).strip()
            for item in payload.get("output_media_types", [])
            if isinstance(item, str) and item.strip()
        ],
        "tags": tags,
        "runtime_image": str(
            (payload.get("runtime") or {}).get("image_ref", "")
            if isinstance(payload.get("runtime"), dict)
            else ""
        ).strip(),
        "dockerfile_path": str(
            (payload.get("runtime") or {}).get("dockerfile_path", "")
            if isinstance(payload.get("runtime"), dict)
            else ""
        ).strip(),
        "workflow_path": str(
            (payload.get("runtime") or {}).get("workflow_path", "")
            if isinstance(payload.get("runtime"), dict)
            else ""
        ).strip(),
        "inputs_json_path": inputs_json_path,
        "entry_workflow": str(
            (payload.get("runtime") or {}).get("entry_workflow", "")
            if isinstance(payload.get("runtime"), dict)
            else ""
        ).strip(),
        "source_repo": str(payload.get("source_repo", "")).strip(),
        "source_commit": str(payload.get("source_commit", "")).strip(),
        "inputs": [
            item for item in payload.get("inputs", []) if isinstance(item, dict)
        ],
        "outputs": [
            item for item in payload.get("outputs", []) if isinstance(item, dict)
        ],
        "expected_outputs": [
            str(item).strip()
            for item in payload.get("expected_outputs", [])
            if isinstance(item, str) and item.strip()
        ],
        "operator_path": str(operator_path),
        "_score": score,
    }


def _rank_benchmark_operator_records_locally(
    *,
    workspace_root: Path,
    excluded_tools: set[str],
    query: str,
) -> list[dict[str, object]]:
    scored: dict[str, tuple[int, int, dict[str, object]]] = {}
    for store_root in _candidate_operator_store_roots(workspace_root):
        rank = 0
        for operator_path in sorted(store_root.glob("operators/*/operator.json")):
            try:
                payload = json.loads(operator_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            candidate = _benchmark_candidate_from_operator_payload(
                payload=payload,
                operator_path=operator_path,
                excluded_tools=excluded_tools,
            )
            if candidate is None:
                continue
            name = str(candidate.get("name", "")).strip()
            text = "\n".join(
                [
                    name,
                    str(candidate.get("summary", "")),
                    str(candidate.get("canonical_text", "")),
                ]
            )
            score = 5 * _benchmark_query_overlap_score(
                query=query, searchable_text=text
            )
            score += _benchmark_intent_hint_score(query=query, searchable_text=text)
            score += int(candidate.pop("_score"))
            candidate["score"] = score
            candidate["rank"] = rank
            current = scored.get(name)
            if (
                current is None
                or score > current[0]
                or (score == current[0] and rank < current[1])
            ):
                scored[name] = (score, rank, candidate)
            rank += 1
    ranked = sorted(
        scored.values(),
        key=lambda item: (-item[0], item[1], str(item[2].get("name", "")).casefold()),
    )
    return [item[2] for item in ranked]


def _task_explicitly_mentions_benchmark_tool(task: str, name: str) -> bool:
    lowered_task = task.casefold()
    lowered_name = name.casefold().strip()
    if not lowered_name:
        return False
    if lowered_name in lowered_task:
        return True
    normalized_name = re.sub(r"[^a-z0-9]+", "", lowered_name)
    if len(normalized_name) <= 3:
        return bool(
            normalized_name
            and re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_name)}(?![a-z0-9])",
                lowered_task,
            )
        )
    normalized_task = re.sub(r"[^a-z0-9]+", "", lowered_task)
    return bool(normalized_name) and normalized_name in normalized_task


def _benchmark_candidate_shared_input_signature(
    candidate: dict[str, object],
) -> tuple[str, ...]:
    paths: list[str] = []
    for item in candidate.get("inputs", []):
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path", "")).strip()
        name = str(item.get("name", "")).strip().casefold()
        if not raw_path:
            continue
        path = Path(raw_path)
        basename = path.name.casefold()
        if basename in {
            "inputs.json",
            "input.json",
            "config.json",
            "config.yaml",
            "config.yml",
        }:
            continue
        if name in {"inputs.json", "input.json"}:
            continue
        if path.suffix.casefold() in {".json", ".yaml", ".yml"} and (
            "input" in basename or "config" in basename
        ):
            continue
        try:
            resolved = str(path.resolve())
        except OSError:
            resolved = str(path)
        paths.append(resolved)
    return tuple(sorted(dict.fromkeys(paths)))


def _benchmark_case_dir_for_tool(*, benchmark_root: str, tool_name: str) -> Path | None:
    root = Path(benchmark_root)
    if not benchmark_root or not root.exists() or not root.is_dir():
        return None
    normalized_tool = re.sub(r"[^a-z0-9]+", "", tool_name.casefold())
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        normalized_name = re.sub(r"^[0-9]+[_-]*", "", child.name.casefold())
        normalized_name = re.sub(r"[^a-z0-9]+", "", normalized_name)
        if normalized_name == normalized_tool:
            return child
    return None


def _benchmark_case_input_signature_from_benchmark_root(
    *,
    benchmark_root: str,
    tool_name: str,
) -> tuple[str, ...]:
    case_dir = _benchmark_case_dir_for_tool(
        benchmark_root=benchmark_root, tool_name=tool_name
    )
    if case_dir is None:
        return ()
    inputs_path: Path | None = None
    for candidate_name in ("inputs.json", "input.json"):
        candidate_path = case_dir / candidate_name
        if candidate_path.exists():
            inputs_path = candidate_path
            break
    if inputs_path is None:
        return ()
    try:
        payload = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    benchmark_root_path = Path(benchmark_root)
    repo_root = (
        benchmark_root_path.parents[2]
        if len(benchmark_root_path.parents) >= 3
        else benchmark_root_path.parent
    )
    discovered: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                visit(nested)
            return
        if isinstance(value, list):
            for nested in value:
                visit(nested)
            return
        if not isinstance(value, str):
            return
        raw = value.strip()
        if not raw:
            return
        raw_path = Path(raw)
        known_data_suffixes = {
            ".fastq",
            ".fq",
            ".gz",
            ".fasta",
            ".fa",
            ".fna",
            ".gfa",
            ".bam",
            ".bai",
            ".csi",
            ".sam",
            ".pdb",
            ".pdbqt",
            ".bed",
            ".tsv",
            ".csv",
            ".txt",
        }
        looks_path_like = (
            raw_path.is_absolute()
            or "/" in raw
            or "\\" in raw
            or raw_path.suffix.casefold() in known_data_suffixes
        )
        candidate_paths: list[Path] = []
        if raw_path.is_absolute():
            candidate_paths.append(raw_path)
        else:
            candidate_paths.extend(
                [repo_root / raw_path, case_dir / raw_path, raw_path]
            )
        for path in candidate_paths:
            if path.exists():
                try:
                    discovered.append(str(path.resolve()))
                except OSError:
                    discovered.append(str(path))
                break
        else:
            if looks_path_like:
                normalized = (
                    str((repo_root / raw_path).resolve())
                    if not raw_path.is_absolute()
                    else str(raw_path)
                )
                discovered.append(normalized)

    visit(payload)
    return tuple(sorted(dict.fromkeys(discovered)))


def _benchmark_case_local_workflow_path(case_dir: Path | None) -> str:
    if case_dir is None:
        return ""
    preferred = case_dir / "workflow.wdl"
    if preferred.exists():
        try:
            return str(preferred.resolve())
        except OSError:
            return str(preferred)
    candidates = sorted(case_dir.glob("*.wdl"))
    if not candidates:
        return ""
    path = candidates[0]
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _select_benchmark_candidate_subset(
    *,
    task: str,
    candidates: list[dict[str, object]],
    benchmark_root: str = "",
) -> list[dict[str, object]]:
    if not candidates:
        return []
    explicitly_named = [
        candidate
        for candidate in candidates
        if _task_explicitly_mentions_benchmark_tool(
            task,
            str(candidate.get("name", "")).strip(),
        )
    ]
    if explicitly_named:
        return explicitly_named
    shared_groups: dict[tuple[str, ...], list[dict[str, object]]] = {}
    for candidate in candidates:
        name = str(candidate.get("name", "")).strip()
        signature = _benchmark_case_input_signature_from_benchmark_root(
            benchmark_root=benchmark_root,
            tool_name=name,
        ) or _benchmark_candidate_shared_input_signature(candidate)
        if not signature:
            continue
        shared_groups.setdefault(signature, []).append(candidate)
    ranked_groups = sorted(
        (group for group in shared_groups.values() if len(group) >= 2),
        key=lambda group: (
            -len(group),
            -sum(int(item.get("score", 0)) for item in group),
            min(int(item.get("rank", 0)) for item in group),
            ",".join(str(item.get("name", "")).casefold() for item in group),
        ),
    )
    if ranked_groups:
        return ranked_groups[0]
    preferred_count = 3 if _task_requests_multiple_benchmark_tools(task) else 1
    return candidates[: max(1, preferred_count)]


def _benchmark_register_agentic_selection_enabled() -> bool:
    value = (
        get_env(
            _BENCHMARK_REGISTER_AGENTIC_SELECTION_ENV,
            _DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION,
        )
        or _DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION
    ).strip()
    return value.lower() not in {"0", "false", "no", "off"}


def _benchmark_register_agentic_selection_timeout_seconds() -> float:
    raw_value = (
        get_env(
            _BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_ENV,
            str(_DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_SECONDS),
        )
        or str(_DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_SECONDS)
    ).strip()
    try:
        timeout = float(raw_value)
    except ValueError:
        timeout = _DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_SECONDS
    return (
        timeout
        if timeout > 0
        else _DEFAULT_BENCHMARK_REGISTER_AGENTIC_SELECTION_TIMEOUT_SECONDS
    )


async def _invoke_benchmark_register_selector(
    *,
    selector: Any,
    prompt: str,
    timeout_seconds: float,
) -> tuple[Any | None, dict[str, object]]:
    """Invoke the register selector as a no-tools model when possible.

    Benchmark register needs semantic judgment, but it is still a pure JSON
    selection step. Prefer direct chat-model messages so the selector does not
    enter the full workspace tool graph. The fallback keeps unit tests and
    older call sites working when a workspace agent is passed explicitly.
    """

    direct_messages = [
        SystemMessage(content=prompt),
        HumanMessage(content="Return JSON only. Do not call tools."),
    ]
    debug: dict[str, object] = {"mode": "direct_messages"}
    internal_config = {
        "callbacks": [],
        "run_name": _INTERNAL_BENCHMARK_REGISTER_SELECTOR_TAG,
        "tags": [_INTERNAL_BENCHMARK_REGISTER_SELECTOR_TAG],
    }
    try:
        result = await asyncio.wait_for(
            selector.ainvoke(direct_messages, config=internal_config),
            timeout=timeout_seconds,
        )
        return result, debug
    except asyncio.TimeoutError:
        debug["failure_reason"] = "direct_invoke_timeout"
        debug["timeout_seconds"] = timeout_seconds
        return None, debug
    except Exception as direct_exc:
        debug["direct_error"] = f"{type(direct_exc).__name__}: {direct_exc}"

    invoke_payload, invoke_kwargs = _build_worker_invoke_request(prompt)
    debug["mode"] = "worker_agent_fallback"
    try:
        result = await asyncio.wait_for(
            selector.ainvoke(invoke_payload, config=internal_config, **invoke_kwargs),
            timeout=timeout_seconds,
        )
        return result, debug
    except asyncio.TimeoutError:
        debug["failure_reason"] = "fallback_invoke_timeout"
        debug["timeout_seconds"] = timeout_seconds
        return None, debug
    except Exception as fallback_exc:
        debug["failure_reason"] = "fallback_invoke_exception"
        debug["fallback_error"] = f"{type(fallback_exc).__name__}: {fallback_exc}"
        return None, debug


def _build_benchmark_register_selection_prompt(
    *,
    task: str,
    candidates: list[dict[str, object]],
    benchmark_root: str,
    excluded_tools: set[str],
    dataset_candidate: dict[str, object],
) -> str:
    lines = [
        "You are selecting benchmark operators for one already-chosen shared dataset.",
        "Return JSON only.",
        "Do not call tools.",
        "Do not inspect files, run shell commands, browse the web, or delegate.",
        "",
        "Rules:",
        "- The shared dataset is already fixed for this benchmark.",
        "- Only choose from the provided operator candidates.",
        "- After choosing the dataset, choose only tools that are compatible with that same dataset.",
        "- By default, choose as many compatible tools as possible when they can run on the chosen shared dataset while still satisfying the user request.",
        "- Prefer semantic fit to the user request, then compatibility with inputs/outputs, then stronger validation status.",
        "- If the request implies docking, pay close attention to pdbqt/receptor/ligand clues.",
        "- If the request implies sequence or protein language modeling, prefer fasta/protein/scoring clues.",
        "- If the request implies assembly, prefer assemblers instead of generic downstream analysis tools.",
        f"- Excluded tools: {', '.join(sorted(excluded_tools)) or 'none'}",
        "",
        "Return schema:",
        '{"selected_tools":["tool_name"],"selection_rationale":"short explanation"}',
        "",
        "User task:",
        task,
        "",
        f"Benchmark root: {benchmark_root or 'unknown'}",
        "",
        "Chosen shared dataset:",
        (
            f"- dataset_id={dataset_candidate.get('dataset_id')} | "
            f"name={dataset_candidate.get('name')} | "
            f"domain={dataset_candidate.get('domain')} | "
            f"files={_dataset_store_files_preview(dataset_candidate)}"
        ),
        "",
    ]
    lines.append("Operator candidates:")
    for index, candidate in enumerate(candidates, start=1):
        lines.append(
            (
                f"{index}. name={candidate.get('name')} | family={candidate.get('family')} | "
                f"status={candidate.get('validation_status')} | inputs={candidate.get('input_media_types')} | "
                f"outputs={candidate.get('output_media_types')} | tags={candidate.get('tags')} | "
                f"summary={candidate.get('summary')}"
            )
        )
    return "\n".join(lines)


def _build_benchmark_register_exploratory_selection_prompt(
    *,
    task: str,
    candidates: list[dict[str, object]],
    dataset_options: list[dict[str, object]],
    benchmark_root: str,
    excluded_tools: set[str],
) -> str:
    lines = [
        "You are selecting operators for an exploratory local benchmark run.",
        "Return JSON only.",
        "Do not call tools.",
        "Do not inspect files, run shell commands, browse the web, or delegate.",
        "",
        "Mode:",
        "- The user did not fix one concrete dataset for every tool.",
        "- Choose useful tools even when no single shared dataset covers them all.",
        "- If a tool can reasonably run on FASTQ even though an old manifest used FASTA, keep it selectable and let the execution agent try the staged FASTQ case.",
        "- A failed run is acceptable; do not reject a useful tool only because compatibility is uncertain.",
        "- When tools use different datasets, the final summary must disclose that and must not claim a fair quality comparison.",
        f"- Excluded tools: {', '.join(sorted(excluded_tools)) or 'none'}",
        "",
        "Return schema:",
        '{"selected_tools":["tool_name"],"tool_dataset_keys":{"tool_name":"dataset_id_or_empty"},"selection_rationale":"short explanation"}',
        "",
        "User task:",
        task,
        "",
        f"Benchmark root: {benchmark_root or 'unknown'}",
        "",
        "Dataset options:",
    ]
    if dataset_options:
        for index, dataset_candidate in enumerate(dataset_options, start=1):
            lines.append(
                (
                    f"{index}. dataset_id={dataset_candidate.get('dataset_id')} | "
                    f"name={dataset_candidate.get('name')} | "
                    f"domain={dataset_candidate.get('domain')} | "
                    f"files={_dataset_store_files_preview(dataset_candidate)}"
                )
            )
    else:
        lines.append("- none; tools may fall back to operator-store manifest inputs.")
    lines.extend(["", "Operator candidates:"])
    for index, candidate in enumerate(candidates, start=1):
        compatible_dataset_ids = [
            str(dataset.get("dataset_id", "")).strip()
            for dataset in dataset_options
            if str(dataset.get("dataset_id", "")).strip()
            and _benchmark_operator_compatible_with_dataset(
                operator=candidate,
                dataset_candidate=dataset,
            )
        ][:4]
        lines.append(
            (
                f"{index}. name={candidate.get('name')} | family={candidate.get('family')} | "
                f"status={candidate.get('validation_status')} | inputs={candidate.get('input_media_types')} | "
                f"outputs={candidate.get('output_media_types')} | tags={candidate.get('tags')} | "
                f"compatible_datasets={compatible_dataset_ids or ['operator_manifest_fallback']} | "
                f"summary={candidate.get('summary')}"
            )
        )
    return "\n".join(lines)


def _build_benchmark_dataset_selection_prompt(
    *,
    task: str,
    dataset_options: list[dict[str, object]],
    benchmark_root: str,
) -> str:
    lines = [
        "You are selecting the one shared dataset for a local benchmark run.",
        "Return JSON only.",
        "Do not call tools.",
        "Do not inspect files, run shell commands, browse the web, or delegate.",
        "",
        "Rules:",
        "- Choose exactly one dataset from the provided options.",
        "- Prefer the dataset that best matches the user task semantically and supports a fair comparison for multiple tools.",
        "- If the request implies assembly, prefer assembly datasets over unrelated FASTQ datasets.",
        "- If the request implies long-read assembly, prefer PacBio/HiFi/ONT long-read datasets and avoid short-read or unrelated domain datasets.",
        "- Do not choose a dataset just because one tool already has stale local inputs for it.",
        "",
        "Return schema:",
        '{"selected_dataset_id":"dataset_id","selection_rationale":"short explanation"}',
        "",
        "User task:",
        task,
        "",
        f"Benchmark root: {benchmark_root or 'unknown'}",
        "",
        "Dataset options:",
    ]
    for index, dataset_candidate in enumerate(dataset_options, start=1):
        lines.append(
            (
                f"{index}. dataset_id={dataset_candidate.get('dataset_id')} | "
                f"name={dataset_candidate.get('name')} | "
                f"domain={dataset_candidate.get('domain')} | "
                f"files={_dataset_store_files_preview(dataset_candidate)}"
            )
        )
    return "\n".join(lines)


async def _select_benchmark_dataset_with_agent(
    *,
    agent,
    task: str,
    dataset_options: list[dict[str, object]],
    benchmark_root: str,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    debug_payload: dict[str, object] = {
        "task": task,
        "benchmark_root": benchmark_root,
        "dataset_option_ids": [
            str(item.get("dataset_id", "")).strip()
            for item in dataset_options
            if str(item.get("dataset_id", "")).strip()
        ],
        "attempts": [],
    }
    if not dataset_options:
        debug_payload["failure_reason"] = "no_dataset_options"
        return None, debug_payload
    prompt = _build_benchmark_dataset_selection_prompt(
        task=task,
        dataset_options=dataset_options,
        benchmark_root=benchmark_root,
    )
    timeout_seconds = _benchmark_register_agentic_selection_timeout_seconds()
    result, invoke_debug = await _invoke_benchmark_register_selector(
        selector=agent,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
    )
    debug_payload["selector_invocation"] = invoke_debug
    if result is None:
        debug_payload["failure_reason"] = "agent_invoke_failed"
        if invoke_debug.get("failure_reason") == "direct_invoke_timeout":
            debug_payload["failure_reason"] = "agent_invoke_timeout"
        if invoke_debug.get("failure_reason") == "fallback_invoke_timeout":
            debug_payload["failure_reason"] = "agent_invoke_timeout"
        if "timeout_seconds" in invoke_debug:
            debug_payload["timeout_seconds"] = invoke_debug["timeout_seconds"]
        return None, debug_payload
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if messages:
        refusal_message = _extract_messages_refusal(messages)
        if refusal_message is not None:
            debug_payload["failure_reason"] = "model_refusal"
            debug_payload["attempts"] = [{"raw_output": refusal_message}]
            return None, debug_payload
        text = _last_ai_text(messages)
    else:
        refusal_message = _extract_model_refusal_message(result)
        if refusal_message is not None:
            debug_payload["failure_reason"] = "model_refusal"
            debug_payload["attempts"] = [{"raw_output": refusal_message}]
            return None, debug_payload
        text = _message_text(result)
    debug_payload["attempts"] = [{"raw_output": text}]
    parsed = _extract_generic_json_payload(text)
    selected_dataset_id = ""
    selection_source = "agent_json"
    if parsed is not None:
        selected_dataset_id = str(parsed.get("selected_dataset_id", "")).strip()
    if not selected_dataset_id and text.strip():
        selected_dataset_id = _benchmark_dataset_id_from_text(
            text=text,
            dataset_options=dataset_options,
        )
        if selected_dataset_id:
            selection_source = "agent_text_fallback"
    debug_payload["selected_dataset_id"] = selected_dataset_id
    debug_payload["selection_source"] = selection_source
    for candidate in dataset_options:
        if str(candidate.get("dataset_id", "")).strip() == selected_dataset_id:
            return candidate, debug_payload
    debug_payload["failure_reason"] = "dataset_not_selected"
    return None, debug_payload


def _benchmark_dataset_id_from_text(
    *,
    text: str,
    dataset_options: list[dict[str, object]],
) -> str:
    normalized_text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text.casefold())
    for candidate in dataset_options:
        dataset_id = str(candidate.get("dataset_id", "")).strip()
        if not dataset_id:
            continue
        normalized_id = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", dataset_id.casefold())
        if normalized_id and normalized_id in normalized_text:
            return dataset_id
    return ""


def _benchmark_selected_tools_from_text(
    *,
    text: str,
    candidates: list[dict[str, object]],
    excluded_tools: set[str],
) -> list[str]:
    normalized_text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text.casefold())
    selected: list[str] = []
    for candidate in candidates:
        name = str(candidate.get("name", "")).strip()
        if not name or name in excluded_tools:
            continue
        normalized_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", name.casefold())
        if normalized_name and normalized_name in normalized_text:
            selected.append(name)
    return selected


def _benchmark_register_agent_dataset_options(
    *,
    task: str,
    workspace_root: Path,
    operator_candidates: list[dict[str, object]],
    excluded_tools: set[str],
    benchmark_root: str = "",
    limit: int = 6,
) -> list[dict[str, object]]:
    ranked_datasets = _rank_local_dataset_store_candidates(
        task=task,
        workspace_root=workspace_root,
        limit=max(limit * 2, 12),
    )
    if not ranked_datasets:
        return []
    relevant_operators = _select_benchmark_candidate_subset(
        task=task,
        candidates=operator_candidates,
        benchmark_root=benchmark_root,
    )
    if not relevant_operators:
        relevant_operators = operator_candidates

    options: list[tuple[int, int, int, dict[str, object]]] = []
    for dataset_candidate in ranked_datasets:
        compatible = [
            candidate
            for candidate in relevant_operators
            if str(candidate.get("name", "")).strip() not in excluded_tools
            and _benchmark_operator_compatible_with_dataset(
                operator=candidate,
                dataset_candidate=dataset_candidate,
            )
        ]
        compatibility_count = len(compatible)
        if compatibility_count <= 0:
            continue
        score = _benchmark_dataset_task_score(
            task=task, dataset_candidate=dataset_candidate
        )
        shared_bonus = (
            1
            if compatibility_count >= 2
            or compatibility_count == len(relevant_operators)
            else 0
        )
        options.append((compatibility_count, shared_bonus, score, dataset_candidate))
    options.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            -item[2],
            str(item[3].get("dataset_id", "")).casefold(),
        )
    )
    ranked_options = [item[3] for item in options]
    multi_tool_benchmark = len(
        relevant_operators
    ) >= 2 or _task_requests_multiple_benchmark_tools(task)
    if multi_tool_benchmark:
        shared_generic = [
            item
            for item in ranked_options
            if not _dataset_candidate_is_operator_specific(item)
        ]
        if shared_generic:
            ranked_options = shared_generic
    return ranked_options[: max(1, limit)]


def _build_benchmark_case_repair_prompt(
    *,
    repo: str,
    task: str,
    case_dir: Path,
    manifest_payload: dict[str, object],
    ready_payload: dict[str, object],
) -> str:
    wdl_path = str(ready_payload.get("wdl_path", "")).strip()
    inputs_json_path = str(ready_payload.get("inputs_json_path", "")).strip()
    runtime_image = str(ready_payload.get("runtime_image", "")).strip()
    dataset_key = str(manifest_payload.get("dataset_key", "")).strip()
    expected_outputs = manifest_payload.get("expected_outputs", [])
    run_status = _read_json_file(case_dir / "run" / "status.json")
    wdl_status = _read_json_file(case_dir / "wdl" / "status.json")
    failure_reason = ""
    if isinstance(run_status, dict):
        failure_reason = str(run_status.get("failure_reason", "")).strip()
    if not failure_reason and isinstance(wdl_status, dict):
        failure_reason = str(wdl_status.get("failure_reason", "")).strip()

    latest_workflow_dir = _latest_benchmark_wdl_workflow_dir(case_dir)
    stderr_excerpt = ""
    stdout_excerpt = ""
    if latest_workflow_dir is not None:
        stderr_excerpt = _read_text_excerpt(
            _latest_file_matching(latest_workflow_dir, "call-*/stderr.txt"),
            max_chars=4000,
        )
        stdout_excerpt = _read_text_excerpt(
            _latest_file_matching(latest_workflow_dir, "call-*/stdout.txt"),
            max_chars=3000,
        )

    lines = [
        "You are repairing a staged local benchmark case before the deterministic retry runs.",
        "You may inspect and minimally edit the staged WDL or staged inputs JSON if that will fix the retry.",
        "Return JSON only after any edits.",
        "",
        "Hard constraints:",
        f"- Only edit files under: {case_dir / 'wdl'}",
        "- Do not edit any source benchmark assets outside the staged case directory.",
        "- Prefer minimal portability or path fixes over broad workflow rewrites.",
        "- If no safe fix is needed or possible, make no edits and say so.",
        "",
        "Return schema:",
        '{"repaired":true,"modified_files":["/abs/path"],"summary":"short explanation"}',
        "",
        "Case context:",
        f"- repo: {repo}",
        f"- task: {task or 'benchmark retry'}",
        f"- case_dir: {case_dir}",
        f"- dataset_key: {dataset_key or 'unknown'}",
        f"- runtime_image: {runtime_image or 'unknown'}",
        f"- wdl_path: {wdl_path}",
        f"- inputs_json_path: {inputs_json_path}",
        f"- expected_outputs: {expected_outputs if isinstance(expected_outputs, list) else []}",
        f"- manifest phase_status: {manifest_payload.get('phase_status', {})}",
        f"- ready_payload: {ready_payload}",
        f"- prior run status: {run_status if isinstance(run_status, dict) else {}}",
        f"- prior wdl status: {wdl_status if isinstance(wdl_status, dict) else {}}",
    ]
    if failure_reason:
        lines.append(f"- observed failure_reason: {failure_reason}")
    if latest_workflow_dir is not None:
        lines.append(f"- latest miniwdl workflow dir: {latest_workflow_dir}")
    if stderr_excerpt:
        lines.extend(["", "Latest stderr excerpt:", "```text", stderr_excerpt, "```"])
    if stdout_excerpt:
        lines.extend(["", "Latest stdout excerpt:", "```text", stdout_excerpt, "```"])
    lines.extend(
        [
            "",
            "Repair goal:",
            "- make the staged retry more likely to succeed on this machine",
            "- especially fix absolute output paths, write-permission issues, staged input paths, or workflow portability problems",
            "- if you edit the WDL command block, preserve workflow intent and outputs",
        ]
    )
    return "\n".join(lines)


def _materialize_benchmark_selection_cases(
    *,
    run_dir: Path,
    task: str,
    workspace_root: Path,
    benchmark_root: str,
    selected_tools: list[str],
    selected_operators: list[dict[str, object]],
    selection_report: dict[str, object],
) -> list[dict[str, object]]:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    cases_root = run_dir / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)
    dataset_key = str(selection_report.get("dataset_key", "")).strip()
    dataset_strategy = str(
        selection_report.get("dataset_strategy", "")
    ).strip() or _benchmark_dataset_strategy_for_task(task)
    selection_report["dataset_strategy"] = dataset_strategy
    raw_tool_dataset_keys = selection_report.get("tool_dataset_keys")
    tool_dataset_keys: dict[str, str] = (
        {
            str(tool): str(dataset_id).strip()
            for tool, dataset_id in raw_tool_dataset_keys.items()
            if isinstance(tool, str) and str(dataset_id).strip()
        }
        if isinstance(raw_tool_dataset_keys, dict)
        else {}
    )
    if dataset_strategy == "shared_dataset" and not dataset_key and selected_tools:
        selected_dataset = selection_report.get("selected_dataset")
        if isinstance(selected_dataset, dict):
            dataset_key = str(selected_dataset.get("dataset_id", "")).strip()
        if not dataset_key:
            dataset_candidate = _resolve_benchmark_dataset_candidate(
                task=task,
                workspace_root=workspace_root,
                operator_candidates=selected_operators,
                requested_tools=selected_tools,
                excluded_tools=set(),
                benchmark_root=benchmark_root,
            )
            if dataset_candidate is not None:
                dataset_key = str(dataset_candidate.get("dataset_id", "")).strip()
                if dataset_key:
                    selection_report["dataset_key"] = dataset_key
                    if not isinstance(selection_report.get("selected_dataset"), dict):
                        selection_report["selected_dataset"] = dataset_candidate
    if dataset_strategy == "per_operator_dataset" and not tool_dataset_keys:
        tool_dataset_keys, selected_datasets = (
            _resolve_benchmark_dataset_keys_for_tools(
                task=task,
                workspace_root=workspace_root,
                operator_candidates=selected_operators,
                selected_tools=selected_tools,
                excluded_tools=set(),
                benchmark_root=benchmark_root,
            )
        )
        selection_report["tool_dataset_keys"] = tool_dataset_keys
        selection_report["selected_datasets"] = selected_datasets
        unique_dataset_keys = sorted({key for key in tool_dataset_keys.values() if key})
        if len(unique_dataset_keys) == 1 and not dataset_key:
            dataset_key = unique_dataset_keys[0]
            selection_report["dataset_key"] = dataset_key
    selected_dataset_by_key: dict[str, dict[str, object]] = {}
    selected_dataset = selection_report.get("selected_dataset")
    if isinstance(selected_dataset, dict):
        selected_dataset_id = str(selected_dataset.get("dataset_id", "")).strip()
        if selected_dataset_id:
            selected_dataset_by_key[selected_dataset_id] = selected_dataset
    selected_datasets = selection_report.get("selected_datasets")
    if isinstance(selected_datasets, dict):
        for key, value in selected_datasets.items():
            if isinstance(value, dict):
                dataset_id = (
                    str(value.get("dataset_id", "")).strip() or str(key).strip()
                )
                if dataset_id:
                    selected_dataset_by_key[dataset_id] = value
    root_cases: dict[str, dict[str, object]] = {}
    case_rows: list[dict[str, object]] = []
    for operator in selected_operators:
        name = str(operator.get("name", "")).strip()
        if not name or name not in selected_tools:
            continue
        case_dataset_key = tool_dataset_keys.get(name, dataset_key)
        case_dataset_candidate = selected_dataset_by_key.get(case_dataset_key)
        row = _materialize_benchmark_selection_case(
            run_dir=run_dir,
            workspace_root=workspace_root,
            benchmark_root=benchmark_root,
            operator=operator,
            dataset_key=case_dataset_key,
            dataset_candidate=case_dataset_candidate,
            dataset_strategy=dataset_strategy,
            selection_reason=str(
                selection_report.get("agent_selection_rationale", "")
            ).strip()
            or str(selection_report.get("selection_strategy", "")),
        )
        case_rows.append(row)
        root_cases[name] = row["root_case_payload"]  # type: ignore[index]
    benchmark_plan = {
        "task": task,
        "run_dir": str(run_dir),
        "benchmark_root": benchmark_root,
        "phase_order": ["register", "run", "summarize"],
        "case_order": selected_tools,
        "cases": root_cases,
        "selection_strategy": selection_report.get("selection_strategy"),
        "dataset_strategy": dataset_strategy,
    }
    _write_json(run_dir / "benchmark_plan.json", benchmark_plan)
    (run_dir / "benchmark_plan.md").write_text(
        "\n".join(
            [
                "# Benchmark Plan",
                "",
                f"- task: `{task}`",
                f"- benchmark_root: `{benchmark_root or 'none'}`",
                f"- selected_tools: `{', '.join(selected_tools)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_resolution = {
        "run_dir": str(run_dir),
        "benchmark_root": benchmark_root,
        "dataset_strategy": dataset_strategy,
        "repo_to_dataset": {
            repo: str(root_cases.get(repo, {}).get("dataset_key", ""))
            for repo in selected_tools
        },
        "selected_datasets": {
            key: {
                "dataset_id": value.get("dataset_id"),
                "name": value.get("name"),
                "source_kind": value.get("source_kind"),
                "dataset_root": value.get("dataset_root"),
                "files": value.get("files"),
            }
            for key, value in selected_dataset_by_key.items()
        },
    }
    _write_json(run_dir / "dataset_resolution.json", dataset_resolution)
    (run_dir / "dataset_resolution.md").write_text(
        "\n".join(
            [
                "# Dataset Resolution",
                "",
                f"- dataset_strategy: `{dataset_strategy}`",
                *[
                    f"- `{repo}` -> `{dataset_resolution['repo_to_dataset'][repo]}`"
                    for repo in selected_tools
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return [
        {
            "phase": "materialize-selection",
            "stdout": {
                "case_order": selected_tools,
                "case_count": len(case_rows),
            },
        },
        {
            "phase": "resolve-datasets",
            "stdout": dataset_resolution,
        },
    ]


def _materialize_benchmark_selection_case(
    *,
    run_dir: Path,
    workspace_root: Path,
    benchmark_root: str,
    operator: dict[str, object],
    dataset_key: str,
    dataset_candidate: dict[str, object] | None,
    dataset_strategy: str,
    selection_reason: str,
) -> dict[str, object]:
    name = str(operator.get("name", "")).strip()
    case_dir = run_dir / "cases" / name
    (case_dir / "wdl").mkdir(parents=True, exist_ok=True)
    (case_dir / "run").mkdir(parents=True, exist_ok=True)
    (case_dir / "docker").mkdir(parents=True, exist_ok=True)
    selected_input_files, selected_input_source = (
        _benchmark_selected_input_files_for_case(
            operator=operator,
            dataset_key=dataset_key,
            dataset_candidate=dataset_candidate,
            workspace_root=workspace_root,
        )
    )
    runtime_image = str(operator.get("runtime_image", "")).strip()
    workflow_path = str(operator.get("workflow_path", "")).strip()
    inputs_json_path = str(operator.get("inputs_json_path", "")).strip()
    dockerfile_path = str(operator.get("dockerfile_path", "")).strip()
    local_case_dir = _benchmark_case_dir_for_tool(
        benchmark_root=benchmark_root,
        tool_name=name,
    )
    local_workflow_path = _benchmark_case_local_workflow_path(local_case_dir)
    local_dockerfile_path = (
        str((local_case_dir / "Dockerfile").resolve())
        if local_case_dir is not None and (local_case_dir / "Dockerfile").exists()
        else ""
    )
    if local_workflow_path:
        workflow_path = local_workflow_path
    if local_dockerfile_path:
        dockerfile_path = local_dockerfile_path
    expected_outputs = _benchmark_expected_outputs_from_operator(operator)
    metric_keys: list[str] = []
    shared_dataset_mode = dataset_strategy == "shared_dataset"
    constraints = (
        [
            "Use the shared dataset selected during benchmark registration.",
            "Use operator-store supplied workflow and inputs discovered during benchmark registration.",
            "Do not switch to a different case-local dataset unless the shared dataset is truly unavailable and you return a blocker.",
        ]
        if shared_dataset_mode
        else [
            "Use the dataset/input bundle assigned to this operator during benchmark registration.",
            "This exploratory benchmark may assign different datasets to different operators; record the actual dataset and inputs used.",
            "Do not claim a fair same-dataset quality comparison unless all selected operators actually ran on the same dataset.",
        ]
    )
    manifest = {
        "repo_name": name,
        "repo_url": str(operator.get("source_repo", "")).strip(),
        "family": str(operator.get("family", "benchmark")).strip() or "benchmark",
        "dataset_key": dataset_key,
        "dataset_strategy": dataset_strategy,
        "image_tag": runtime_image,
        "runtime_image": runtime_image,
        "repo_native_entry": "",
        "wdl_workflow_name": str(operator.get("entry_workflow", "")).strip() or name,
        "expected_outputs": expected_outputs,
        "metric_keys": metric_keys,
        "constraints": constraints,
        "case_dir": str(case_dir),
        "wdl_path": workflow_path or None,
        "inputs_path": inputs_json_path or None,
        "dockerfile_path": dockerfile_path or None,
        "dockerfile_candidates": [dockerfile_path] if dockerfile_path else [],
        "wdl_candidates": [workflow_path] if workflow_path else [],
        "input_json_candidates": [inputs_json_path] if inputs_json_path else [],
        "repo_native_command_candidates": [],
        "local_result_candidates": expected_outputs,
        "selected_input_source": selected_input_source,
        "selected_input_files": selected_input_files,
        "selected_dataset": dataset_candidate or {},
        "missing_input_keys": [],
        "selection_reason": selection_reason,
        "phase_status": {
            "plan": "completed",
            "prebuild": "pending",
            "dataset_prep": "prepared",
            "execution_ready": "pending",
            "benchmark_run": "pending",
            "analysis": "pending",
            "summary": "pending",
        },
        "paths": {
            "docker_dir": str(case_dir / "docker"),
            "wdl_dir": str(case_dir / "wdl"),
            "run_dir": str(case_dir / "run"),
        },
        "source_case_dir": (
            str(local_case_dir)
            if local_case_dir is not None
            else str(operator.get("operator_path", "")).strip()
        ),
        "source_wdl_path": workflow_path or None,
        "source_inputs_path": inputs_json_path or None,
        "operator_id": str(operator.get("operator_id", "")).strip(),
        "operator_path": str(operator.get("operator_path", "")).strip(),
    }
    _write_json(case_dir / "manifest.json", manifest)
    dataset_selection = {
        "dataset_key": dataset_key,
        "dataset_strategy": dataset_strategy,
        "selected_dataset": dataset_candidate or {},
        "dataset_download_dir": "",
        "selected_input_source": manifest["selected_input_source"],
        "selected_input_files": selected_input_files,
        "selection_complete": True,
        "selection_reason": selection_reason,
        "missing_input_keys": [],
    }
    _write_json(case_dir / "dataset_selection.json", dataset_selection)
    _write_json(
        case_dir / "dataset_manifest.json",
        {
            "dataset_key": dataset_key,
            "dataset_strategy": dataset_strategy,
            "selected_dataset": dataset_candidate or {},
            "selected_input_files": selected_input_files,
            "source": manifest["selected_input_source"],
            "selection_reason": selection_reason,
        },
    )
    (case_dir / "agent_task.md").write_text(
        "\n".join(
            [
                "# Agent Benchmark Task",
                "",
                f"- repo: `{name}`",
                f"- operator_id: `{manifest['operator_id']}`",
                f"- shared_dataset_key: `{dataset_key or 'missing'}`",
                f"- dataset_strategy: `{dataset_strategy}`",
                f"- selected_input_source: `{selected_input_source}`",
                f"- workflow_path: `{workflow_path or 'missing'}`",
                f"- inputs_json_path: `{inputs_json_path or 'missing'}`",
                f"- runtime_image: `{runtime_image or 'missing'}`",
                "",
                "Rules:",
                (
                    "- Use the shared dataset selected by registration for this case."
                    if shared_dataset_mode
                    else "- Use the dataset/input bundle assigned to this operator by registration."
                ),
                (
                    "- Do not fall back to a different local case dataset without first repairing the staged inputs in this case directory."
                    if shared_dataset_mode
                    else "- If the assigned dataset is unusable, you may try the operator-store manifest inputs or a compatible FASTQ/FASTA input implied by the staged workflow, but record the change and evidence clearly."
                ),
                (
                    "- If the staged inputs and declared shared dataset disagree, fix the staged inputs before execution or return a blocker."
                    if shared_dataset_mode
                    else "- This case may use a different dataset from other tools; do not report a fair same-dataset comparison from this case alone."
                ),
                "",
                selection_reason,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    staged_wdl_path = _stage_benchmark_operator_artifact(
        source_path=workflow_path,
        target_path=case_dir
        / "wdl"
        / (Path(workflow_path).name if workflow_path else "workflow.wdl"),
    )
    staged_inputs_path = _stage_benchmark_operator_artifact(
        source_path=inputs_json_path,
        target_path=case_dir / "wdl" / "inputs.json",
    )
    if staged_inputs_path is not None:
        _sanitize_benchmark_inputs_json(
            staged_inputs_path,
            selected_input_files=selected_input_files,
        )
    ready = bool(staged_wdl_path and staged_inputs_path and runtime_image)
    _write_json(
        case_dir / "execution_ready.json",
        {
            "repo": name,
            "dockerfile_path": dockerfile_path or None,
            "wdl_path": str(staged_wdl_path)
            if staged_wdl_path is not None
            else (workflow_path or None),
            "inputs_json_path": str(staged_inputs_path)
            if staged_inputs_path is not None
            else (inputs_json_path or None),
            "repo_native_command_candidates": [],
            "local_result_candidates": expected_outputs,
            "runtime_image": runtime_image,
            "ready": ready,
            "inputs_ready": staged_inputs_path is not None,
            "missing_input_keys": [],
        },
    )
    manifest["phase_status"]["execution_ready"] = "prepared" if ready else "partial"
    _write_json(case_dir / "manifest.json", manifest)
    return {
        "repo": name,
        "root_case_payload": {
            key: value
            for key, value in manifest.items()
            if key
            in {
                "repo_name",
                "repo_url",
                "family",
                "dataset_key",
                "dataset_strategy",
                "image_tag",
                "repo_native_entry",
                "wdl_workflow_name",
                "expected_outputs",
                "constraints",
                "case_dir",
                "wdl_path",
                "inputs_path",
                "dockerfile_path",
                "dockerfile_candidates",
                "wdl_candidates",
                "input_json_candidates",
                "repo_native_command_candidates",
                "local_result_candidates",
            }
        },
    }


def _stage_benchmark_operator_artifact(
    *, source_path: str, target_path: Path
) -> Path | None:
    if not source_path:
        return None
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        return None
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target_path)
    return target_path


def _sanitize_benchmark_inputs_json(
    path: Path,
    *,
    selected_input_files: dict[str, str] | None = None,
) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    selected_input_files = selected_input_files or {}

    def sanitize(value: object, *, key_hint: str = "") -> object:
        if isinstance(value, dict):
            cleaned: dict[str, object] = {}
            for key, nested in value.items():
                if isinstance(key, str) and re.match(
                    r"^_comment", key.strip(), flags=re.IGNORECASE
                ):
                    continue
                cleaned[key] = sanitize(nested, key_hint=str(key))
            return cleaned
        if isinstance(value, list):
            if (
                selected_input_files
                and all(
                    isinstance(item, str)
                    and (
                        item.strip().startswith("/path/to/")
                        or _looks_like_existing_input_path(item.strip())
                    )
                    for item in value
                )
                and _looks_like_fastq_key(key_hint)
            ):
                fastq_candidates = _benchmark_selected_paths_for_suffixes(
                    selected_input_files,
                    suffixes=(".fastq", ".fq", ".fastq.gz", ".fq.gz"),
                )
                if fastq_candidates:
                    return fastq_candidates[: len(value)]
            return [sanitize(item, key_hint=key_hint) for item in value]
        if isinstance(value, str) and selected_input_files:
            stripped_value = value.strip()
            if stripped_value.startswith("/path/to/") or (
                _looks_like_existing_input_path(stripped_value)
                and _looks_like_benchmark_input_key(key_hint)
            ):
                replacement = _benchmark_placeholder_replacement(
                    key_hint=key_hint,
                    placeholder=value,
                    selected_input_files=selected_input_files,
                )
                if replacement:
                    return replacement
        return value

    cleaned_payload = sanitize(payload)
    if cleaned_payload == payload:
        return
    try:
        path.write_text(
            json.dumps(cleaned_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def _looks_like_fastq_key(key_hint: str) -> bool:
    lowered = key_hint.casefold()
    return "fastq" in lowered or "read" in lowered


def _looks_like_benchmark_input_key(key_hint: str) -> bool:
    lowered = key_hint.casefold()
    return (
        _looks_like_fastq_key(key_hint)
        or "fasta" in lowered
        or "gtf" in lowered
        or "reference" in lowered
        or "genome" in lowered
    )


def _looks_like_existing_input_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith(("/", "./", "../")):
        return True
    suffixes = (
        ".fastq",
        ".fq",
        ".fastq.gz",
        ".fq.gz",
        ".fasta",
        ".fa",
        ".fna",
        ".gtf",
        ".json",
        ".csv",
    )
    lowered = value.casefold()
    return any(lowered.endswith(suffix) for suffix in suffixes)


def _benchmark_selected_paths_for_suffixes(
    selected_input_files: dict[str, str],
    *,
    suffixes: tuple[str, ...],
) -> list[str]:
    matches = [
        path
        for name, path in selected_input_files.items()
        if name.casefold().endswith(tuple(item.casefold() for item in suffixes))
    ]
    return sorted(dict.fromkeys(matches))


def _benchmark_placeholder_replacement(
    *,
    key_hint: str,
    placeholder: str,
    selected_input_files: dict[str, str],
) -> str | None:
    placeholder_name = Path(placeholder.strip()).name
    direct = selected_input_files.get(placeholder_name)
    if direct:
        return direct

    lowered_key = key_hint.casefold()
    if (
        lowered_key.endswith("fastq1")
        or lowered_key.endswith("read1")
        or lowered_key.endswith("r1")
    ):
        fastq_candidates = _benchmark_selected_paths_for_suffixes(
            selected_input_files,
            suffixes=(".fastq", ".fq", ".fastq.gz", ".fq.gz"),
        )
        return fastq_candidates[0] if fastq_candidates else None
    if (
        lowered_key.endswith("fastq2")
        or lowered_key.endswith("read2")
        or lowered_key.endswith("r2")
    ):
        fastq_candidates = _benchmark_selected_paths_for_suffixes(
            selected_input_files,
            suffixes=(".fastq", ".fq", ".fastq.gz", ".fq.gz"),
        )
        return fastq_candidates[1] if len(fastq_candidates) > 1 else None
    if _looks_like_fastq_key(key_hint):
        fastq_candidates = _benchmark_selected_paths_for_suffixes(
            selected_input_files,
            suffixes=(".fastq", ".fq", ".fastq.gz", ".fq.gz"),
        )
        return fastq_candidates[0] if fastq_candidates else None
    if "gtf" in lowered_key:
        gtf_candidates = _benchmark_selected_paths_for_suffixes(
            selected_input_files,
            suffixes=(".gtf",),
        )
        return gtf_candidates[0] if gtf_candidates else None
    if (
        "fasta" in lowered_key
        or lowered_key.endswith("genome_fasta")
        or lowered_key.endswith("reference_fasta")
    ):
        fasta_candidates = _benchmark_selected_paths_for_suffixes(
            selected_input_files,
            suffixes=(".fa", ".fasta", ".fna"),
        )
        if fasta_candidates:
            return fasta_candidates[0]
        if "reference" not in lowered_key and "genome" not in lowered_key:
            fastq_candidates = _benchmark_selected_paths_for_suffixes(
                selected_input_files,
                suffixes=(".fastq", ".fq", ".fastq.gz", ".fq.gz"),
            )
            return fastq_candidates[0] if fastq_candidates else None
        return None
    for suffix in (".bwt", ".pac", ".ann", ".amb", ".sa", ".csv"):
        if lowered_key.endswith(
            suffix.lstrip(".")
        ) or placeholder_name.casefold().endswith(suffix):
            candidates = _benchmark_selected_paths_for_suffixes(
                selected_input_files,
                suffixes=(suffix,),
            )
            return candidates[0] if candidates else None
    return None


def _benchmark_selected_input_files_from_operator(
    operator: dict[str, object],
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for item in operator.get("inputs", []):
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path", "")).strip()
        name = str(item.get("name", "")).strip()
        if not raw_path or not name:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        selected[name] = str(path)
    return selected


def _benchmark_selected_input_files_for_case(
    *,
    operator: dict[str, object],
    dataset_key: str,
    dataset_candidate: dict[str, object] | None = None,
    workspace_root: Path,
) -> tuple[dict[str, str], str]:
    candidate_selected = _benchmark_selected_input_files_from_dataset_candidate(
        dataset_candidate=dataset_candidate,
        dataset_key=dataset_key,
    )
    if candidate_selected:
        source_kind = (
            str(dataset_candidate.get("source_kind", "")).strip()
            if dataset_candidate
            else ""
        )
        return candidate_selected, source_kind or "selected_dataset"
    dataset_selected = _benchmark_selected_input_files_from_dataset_store(
        operator=operator,
        dataset_key=dataset_key,
        workspace_root=workspace_root,
    )
    if dataset_selected:
        return dataset_selected, "dataset_store"
    selected = _benchmark_selected_input_files_from_operator(operator)
    if selected:
        return selected, "operator_store_manifest"
    return {}, "missing_inputs"


def _benchmark_selected_input_files_from_dataset_candidate(
    *,
    dataset_candidate: dict[str, object] | None,
    dataset_key: str,
) -> dict[str, str]:
    if not isinstance(dataset_candidate, dict):
        return {}
    candidate_id = str(dataset_candidate.get("dataset_id", "")).strip()
    if dataset_key.strip() and candidate_id and candidate_id != dataset_key.strip():
        return {}
    files = dataset_candidate.get("files")
    if not isinstance(files, list):
        return {}
    selected: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri", "")).strip()
        if not uri:
            continue
        path = Path(uri)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        if not path.exists() or not path.is_file():
            continue
        path_text = str(path)
        name = str(item.get("name", "")).strip()
        role = str(item.get("role", "")).strip()
        if name:
            selected[name] = path_text
        if role and role not in selected:
            selected[role] = path_text
        filename = path.name
        if filename and filename not in selected:
            selected[filename] = path_text
    return selected


def _benchmark_selected_input_files_from_dataset_store(
    *,
    operator: dict[str, object],
    dataset_key: str,
    workspace_root: Path,
) -> dict[str, str]:
    dataset_key = dataset_key.strip()
    if not dataset_key:
        return {}
    operator_id = str(operator.get("operator_id", "")).strip()
    for store_root in _candidate_dataset_store_roots(workspace_root):
        try:
            store = DatasetStore(store_root)
            rows = store.search_datasets(
                DatasetSearchFilter(dataset_id=dataset_key, limit=3)
            )
        except sqlite3.Error:
            continue
        for row in rows:
            if str(row.get("dataset_id", "")).strip() != dataset_key:
                continue
            record_path_raw = row.get("record_path")
            if not isinstance(record_path_raw, str) or not record_path_raw.strip():
                continue
            record_path = Path(record_path_raw.strip())
            if not record_path.is_absolute():
                project_relative = _PROJECT_ROOT / record_path
                if project_relative.exists():
                    record_path = project_relative
            payload = _read_json_file(record_path)
            if not isinstance(payload, dict):
                continue
            compatible_ids = {
                str(item).strip()
                for item in payload.get("compatible_operator_ids", [])
                if str(item).strip()
            }
            if compatible_ids and operator_id and operator_id not in compatible_ids:
                continue
            files = payload.get("files")
            if not isinstance(files, list):
                continue
            selected: dict[str, str] = {}
            for item in files:
                if not isinstance(item, dict):
                    continue
                uri = str(item.get("uri", "")).strip()
                name = str(item.get("name", "")).strip()
                role = str(item.get("role", "")).strip()
                if not uri:
                    continue
                path = Path(uri)
                if not path.is_absolute():
                    path = _PROJECT_ROOT / uri
                if not path.exists() or not path.is_file():
                    continue
                if name:
                    selected[name] = str(path)
                if role and role not in selected:
                    selected[role] = str(path)
                filename = path.name
                if filename and filename not in selected:
                    selected[filename] = str(path)
            if selected:
                return selected
    return {}


def _benchmark_expected_outputs_from_operator(operator: dict[str, object]) -> list[str]:
    expected_outputs = [
        str(item).strip()
        for item in operator.get("expected_outputs", [])
        if isinstance(item, str) and item.strip()
    ]
    if expected_outputs:
        return expected_outputs
    outputs: list[str] = []
    for item in operator.get("outputs", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if path:
            outputs.append(path)
    return outputs


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _sha256_jsonable(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _benchmark_selected_input_names(selected_input_files: dict[str, str]) -> list[str]:
    return sorted(str(name) for name in selected_input_files.keys())


def _benchmark_input_signature_from_manifest(manifest: dict[str, object]) -> str:
    selected_input_files = manifest.get("selected_input_files", {})
    if isinstance(selected_input_files, dict) and selected_input_files:
        normalized = {
            str(key): str(value) for key, value in selected_input_files.items()
        }
        return _sha256_jsonable(normalized)
    inputs_path_raw = manifest.get("inputs_path")
    if isinstance(inputs_path_raw, str) and inputs_path_raw.strip():
        inputs_path = Path(inputs_path_raw.strip())
        if inputs_path.exists():
            return _sha256_file(inputs_path)
    return ""


def _benchmark_workflow_signature_from_manifest(manifest: dict[str, object]) -> str:
    workflow_path_raw = manifest.get("wdl_path") or manifest.get("source_wdl_path")
    if not isinstance(workflow_path_raw, str) or not workflow_path_raw.strip():
        return ""
    workflow_path = Path(workflow_path_raw.strip())
    if not workflow_path.exists():
        return ""
    return _sha256_file(workflow_path)


def _benchmark_result_query(
    *,
    repo: str,
    task: str,
    manifest: dict[str, object],
) -> str:
    dataset_key = str(manifest.get("dataset_key", "")).strip()
    workflow_name = str(manifest.get("wdl_workflow_name", "")).strip()
    selected_input_files = manifest.get("selected_input_files", {})
    input_names = []
    if isinstance(selected_input_files, dict):
        input_names = _benchmark_selected_input_names(
            {str(key): str(value) for key, value in selected_input_files.items()}
        )
    parts = [repo, task, dataset_key, workflow_name, " ".join(input_names[:8])]
    return "\n".join(part for part in parts if part.strip())


def _benchmark_query_overlap_score(*, query: str, searchable_text: str) -> int:
    query_tokens = _tokenize_benchmark_text(query)
    if not query_tokens:
        return 0
    searchable = searchable_text.casefold()
    return sum(token in searchable for token in query_tokens)


def _tokenize_benchmark_text(text: str) -> list[str]:
    return [
        token
        for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", text.casefold())
        if token and len(token) > 1
    ]


def _benchmark_intent_hint_score(*, query: str, searchable_text: str) -> int:
    query_lower = query.casefold()
    searchable_lower = searchable_text.casefold()
    score = 0
    docking_markers = ("dock", "docking", "vina")
    if any(marker in query_lower for marker in docking_markers):
        if any(
            marker in searchable_lower
            for marker in ("dock", "docking", "vina", "pdbqt")
        ):
            score += 25
    structure_markers = ("pdb", "pdbqt", "structure", "structural")
    if any(marker in query_lower for marker in structure_markers):
        if any(marker in searchable_lower for marker in structure_markers):
            score += 10
    sequence_markers = ("sequence", "fasta", "protein", "language model", "esm")
    if any(marker in query_lower for marker in sequence_markers):
        if any(marker in searchable_lower for marker in sequence_markers):
            score += 10
    return score


def _run_deterministic_benchmark_case(
    *,
    node: TaskNode,
    workspace_root: Path,
    repo: str,
) -> WorkerResult:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    run_dir_raw = metadata.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        return WorkerResult(
            status="failed",
            summary=f"Benchmark {repo} runtime is missing run_dir metadata.",
            failure_reason="missing_run_dir",
        )
    return WorkerResult(
        status="failed",
        summary=(
            f"Deterministic benchmark case execution for {repo} has been removed; "
            "benchmark case nodes must now run through the agent-owned execution path."
        ),
        failure_reason="deterministic_benchmark_case_removed",
    )


def _run_deterministic_benchmark_summary(
    *, node: TaskNode, workspace_root: Path
) -> WorkerResult:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    run_dir_raw = metadata.get("run_dir")
    if not isinstance(run_dir_raw, str) or not run_dir_raw.strip():
        return WorkerResult(
            status="failed",
            summary="Benchmark summary helper is missing run_dir metadata.",
            failure_reason="missing_run_dir",
        )
    run_dir = Path(run_dir_raw)
    selected_tools = [
        str(item)
        for item in metadata.get("selected_tools", [])
        if isinstance(item, str) and item.strip()
    ]
    if not selected_tools:
        cases_root = run_dir / "cases"
        if cases_root.exists():
            selected_tools = sorted(
                path.name for path in cases_root.iterdir() if path.is_dir()
            )
    rows: list[dict[str, object]] = []
    artifacts: list[str] = []
    evidence: list[str] = []
    completed_cases = 0
    for repo in selected_tools:
        case_dir = run_dir / "cases" / repo
        manifest_path = case_dir / "manifest.json"
        if not manifest_path.exists():
            rows.append({"repo": repo, "status": "missing_case_manifest"})
            continue
        analysis_paths = _ensure_benchmark_analysis(
            repo=repo,
            run_dir=run_dir,
        )
        artifacts.extend(str(path) for path in analysis_paths if path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        status_path = case_dir / "run" / "status.json"
        analysis_path = case_dir / "analysis.json"
        result_manifest_path = _benchmark_result_manifest_path(case_dir)
        worker_result = _benchmark_case_worker_result(run_dir=run_dir, repo=repo)
        status_payload = (
            json.loads(status_path.read_text(encoding="utf-8"))
            if status_path.exists()
            else {}
        )
        analysis_payload = (
            json.loads(analysis_path.read_text(encoding="utf-8"))
            if analysis_path.exists()
            else {"artifact_paths": [], "metrics": {}, "artifact_checksums": {}}
        )
        result_manifest = (
            _read_json_file(result_manifest_path)
            if result_manifest_path is not None
            else {}
        )
        success = _benchmark_case_completed_from_artifacts(
            worker_result=worker_result,
            run_status=status_payload if isinstance(status_payload, dict) else {},
            analysis_payload=analysis_payload
            if isinstance(analysis_payload, dict)
            else {},
            result_manifest=result_manifest
            if isinstance(result_manifest, dict)
            else {},
        )
        if success:
            completed_cases += 1
        rows.append(
            {
                "repo": repo,
                "dataset_key": manifest.get("dataset_key"),
                "success": success,
                "returncode": _benchmark_case_returncode(
                    worker_result=worker_result,
                    run_status=status_payload
                    if isinstance(status_payload, dict)
                    else {},
                    result_manifest=result_manifest
                    if isinstance(result_manifest, dict)
                    else {},
                ),
                "artifact_paths": _benchmark_case_analysis_artifact_paths(
                    analysis_payload if isinstance(analysis_payload, dict) else {}
                ),
                "metrics": analysis_payload.get("metrics", {}),
            }
        )
        artifacts.extend(
            [
                str(path)
                for path in (
                    status_path,
                    analysis_path,
                    case_dir / "analysis.md",
                    result_manifest_path,
                )
                if path is not None and path.exists()
            ]
        )
        evidence.extend(
            str(path)
            for path in (status_path, analysis_path, result_manifest_path)
            if path is not None and path.exists()
        )
        manifest["phase_status"] = {
            **dict(manifest.get("phase_status", {})),
            "analysis": "completed"
            if analysis_path.exists()
            else manifest.get("phase_status", {}).get("analysis"),
            "summary": "completed",
        }
        _write_json(manifest_path, manifest)

    overall_completed = bool(rows) and completed_cases == len(selected_tools)
    completed_dataset_keys = sorted(
        {
            str(row.get("dataset_key", "")).strip()
            for row in rows
            if row.get("success") is True and str(row.get("dataset_key", "")).strip()
        }
    )
    dataset_consistency = (
        "same_dataset"
        if len(completed_dataset_keys) == 1 and completed_cases >= 2
        else "mixed_or_unverified"
        if len(completed_dataset_keys) > 1
        else "single_or_unknown"
    )
    comparison = _build_benchmark_comparison(rows)
    payload = {
        "run_dir": str(run_dir),
        "selected_tools": selected_tools,
        "case_count": len(selected_tools),
        "completed_cases": completed_cases,
        "status": "completed" if overall_completed else "partial",
        "dataset_consistency": dataset_consistency,
        "comparison": comparison,
        "rows": rows,
    }
    _write_json(run_dir / "benchmark_supervisor_summary.json", payload)
    lines = [
        "# Benchmark Supervisor Summary",
        "",
        f"- run_dir: `{run_dir}`",
        f"- selected_tools: `{', '.join(selected_tools)}`",
        f"- completed_cases: `{completed_cases}` / `{len(selected_tools)}`",
        f"- status: `{payload['status']}`",
        f"- dataset_consistency: `{dataset_consistency}`",
        "",
        "## Rows",
        "",
    ]
    lines.extend(
        f"- `{row['repo']}`: success=`{row.get('success')}`, returncode=`{row.get('returncode')}`, metrics=`{row.get('metrics')}`"
        for row in rows
    )
    if comparison:
        lines.extend(
            [
                "",
                "## Comparison",
                "",
                f"- best_n50: `{comparison['best_n50']}`",
                f"- lowest_contig_count: `{comparison['lowest_contig_count']}`",
                f"- largest_assembly_size: `{comparison['largest_assembly_size']}`",
                f"- overall: {comparison['overall']}",
            ]
        )
    (run_dir / "benchmark_supervisor_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    artifacts.extend(
        [
            str(run_dir / "benchmark_supervisor_summary.json"),
            str(run_dir / "benchmark_supervisor_summary.md"),
        ]
    )
    artifacts.extend(
        _materialize_benchmark_operator_products(
            run_dir=run_dir,
            selected_tools=selected_tools,
            source_repo="",
        )
    )
    evidence.append(str(run_dir / "benchmark_supervisor_summary.json"))
    summary = (
        f"Summarized benchmark results for {', '.join(selected_tools)}; "
        f"{completed_cases}/{len(selected_tools)} cases completed."
    )
    if comparison:
        summary += f" {comparison['overall']}"
    if overall_completed:
        return WorkerResult(
            status="completed",
            summary=summary,
            artifacts=artifacts,
            evidence=evidence,
        )
    return WorkerResult(
        status="partial",
        summary=summary,
        artifacts=artifacts,
        evidence=evidence,
        failure_reason="benchmark_cases_incomplete",
    )


def _benchmark_case_worker_result(*, run_dir: Path, repo: str) -> dict[str, object]:
    payload = _read_json_file(run_dir / "worker_outputs" / f"{repo}.json")
    if not isinstance(payload, dict):
        return {}
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _benchmark_result_manifest_path(case_dir: Path) -> Path | None:
    candidates = [
        case_dir / "run" / "result_manifest.json",
        case_dir / "result_manifest.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _benchmark_case_completed_from_artifacts(
    *,
    worker_result: dict[str, object],
    run_status: dict[str, object],
    analysis_payload: dict[str, object],
    result_manifest: dict[str, object],
) -> bool:
    success_markers = [
        run_status.get("success") is True,
        str(worker_result.get("status", "")).strip() == "completed",
        str(analysis_payload.get("status", "")).strip() == "completed",
        str(result_manifest.get("status", "")).strip() == "completed",
        result_manifest.get("exit_code") == 0,
        (
            isinstance(result_manifest.get("workflow"), dict)
            and result_manifest["workflow"].get("exit_code") == 0
        ),
    ]
    if not any(success_markers):
        return False
    return _benchmark_case_has_output_evidence(
        run_status=run_status,
        analysis_payload=analysis_payload,
        result_manifest=result_manifest,
    )


def _benchmark_case_has_output_evidence(
    *,
    run_status: dict[str, object],
    analysis_payload: dict[str, object],
    result_manifest: dict[str, object],
) -> bool:
    expected_outputs = result_manifest.get("expected_outputs")
    if isinstance(expected_outputs, dict) and expected_outputs:
        if any(
            isinstance(item, dict) and item.get("exists") is True
            for item in expected_outputs.values()
        ):
            return True
    output_checks = result_manifest.get("output_checks")
    if isinstance(output_checks, dict) and output_checks:
        if any(
            isinstance(item, dict)
            and (
                item.get("exists") is True
                or item.get("present") is True
                or int(item.get("size_bytes", 0) or 0) > 0
            )
            for item in output_checks.values()
        ):
            return True
    file_checks = result_manifest.get("file_checks")
    if isinstance(file_checks, dict) and file_checks:
        if any(
            isinstance(item, dict)
            and (
                item.get("exists") is True
                or item.get("present") is True
                or int(item.get("size_bytes", 0) or 0) > 0
            )
            for item in file_checks.values()
        ):
            return True
    outputs = result_manifest.get("outputs")
    if isinstance(outputs, dict) and outputs:
        if any(
            (
                isinstance(item, dict)
                and (
                    item.get("exists") is True
                    or item.get("present") is True
                    or int(item.get("size_bytes", 0) or 0) > 0
                )
            )
            or (isinstance(item, str) and bool(item.strip()))
            for item in outputs.values()
        ):
            return True
    analysis_checks = analysis_payload.get("output_checks")
    if isinstance(analysis_checks, dict) and analysis_checks:
        if any(
            isinstance(item, dict)
            and (
                item.get("present") is True
                or item.get("exists") is True
                or int(item.get("size_bytes", 0) or 0) > 0
            )
            for item in analysis_checks.values()
        ):
            return True
    output_presence = analysis_payload.get("output_presence")
    if isinstance(output_presence, dict) and output_presence:
        if any(value is True for value in output_presence.values()):
            return True
    output_sizes = analysis_payload.get("output_sizes_bytes")
    if isinstance(output_sizes, dict) and output_sizes:
        if any(int(value or 0) > 0 for value in output_sizes.values()):
            return True
    checks = analysis_payload.get("checks")
    if isinstance(checks, dict):
        if any(
            key.endswith("_present") and value is True for key, value in checks.items()
        ):
            return True
    if analysis_payload.get("real_contigs_fasta_present") is True:
        return True
    output_artifacts = run_status.get("output_artifacts")
    if isinstance(output_artifacts, list) and output_artifacts:
        return True
    return False


def _benchmark_case_returncode(
    *,
    worker_result: dict[str, object],
    run_status: dict[str, object],
    result_manifest: dict[str, object],
) -> int | None:
    returncode = run_status.get("returncode")
    if isinstance(returncode, int):
        return returncode
    workflow = result_manifest.get("workflow")
    if isinstance(workflow, dict):
        workflow_exit = workflow.get("exit_code")
        if isinstance(workflow_exit, int):
            return workflow_exit
    manifest_exit = result_manifest.get("exit_code")
    if isinstance(manifest_exit, int):
        return manifest_exit
    if str(worker_result.get("status", "")).strip() == "completed":
        return 0
    return None


def _benchmark_case_analysis_artifact_paths(
    analysis_payload: dict[str, object],
) -> list[str]:
    artifact_paths = analysis_payload.get("artifact_paths")
    if isinstance(artifact_paths, list) and artifact_paths:
        return [str(item) for item in artifact_paths if str(item).strip()]
    artifacts = analysis_payload.get("artifacts")
    if isinstance(artifacts, dict):
        return [
            str(value)
            for value in artifacts.values()
            if isinstance(value, str) and value.strip()
        ]
    return []


def _build_benchmark_comparison(rows: list[dict[str, object]]) -> dict[str, str] | None:
    completed_rows = [
        row
        for row in rows
        if row.get("success") is True and isinstance(row.get("metrics"), dict)
    ]
    if not completed_rows:
        return None
    dataset_keys = {
        str(row.get("dataset_key", "")).strip()
        for row in completed_rows
        if str(row.get("dataset_key", "")).strip()
    }
    if len(dataset_keys) > 1:
        return None

    best_n50 = _best_metric_repo(completed_rows, "n50", higher_is_better=True)
    lowest_contigs = _best_metric_repo(
        completed_rows, "contig_count", higher_is_better=False
    )
    largest_assembly = _best_metric_repo(
        completed_rows, "assembly_size", higher_is_better=True
    )
    if not any((best_n50, lowest_contigs, largest_assembly)):
        return None
    winners = [repo for repo in (best_n50, largest_assembly) if repo]
    if winners:
        overall_repo = max(set(winners), key=winners.count)
    else:
        overall_repo = lowest_contigs

    if overall_repo and lowest_contigs and overall_repo != lowest_contigs:
        overall = (
            f"Overall favors {overall_repo} by N50/assembly-size strength, "
            f"while {lowest_contigs} has the lower contig_count."
        )
    elif overall_repo:
        overall = (
            f"Overall favors {overall_repo} across the available comparison signals."
        )
    else:
        overall = "No single best tool could be identified from the available metrics."

    return {
        "best_n50": best_n50 or "unknown",
        "lowest_contig_count": lowest_contigs or "unknown",
        "largest_assembly_size": largest_assembly or "unknown",
        "overall": overall,
    }


def _best_metric_repo(
    rows: list[dict[str, object]],
    metric_name: str,
    *,
    higher_is_better: bool,
) -> str | None:
    scored: list[tuple[float, str]] = []
    for row in rows:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        value = metrics.get(metric_name)
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        repo = row.get("repo")
        if isinstance(repo, str) and repo:
            scored.append((float(value), repo))
    if not scored:
        return None
    value, repo = (max if higher_is_better else min)(scored, key=lambda item: item[0])
    return repo


def _benchmark_repo_from_node_id(node_id: str) -> str | None:
    candidate = node_id.removeprefix("retry_")
    if candidate in {"register", "summarize"} or _looks_like_user_delivery_node(
        candidate
    ):
        return None
    return candidate or None


def _status_payload_is_success(status_path: Path) -> bool:
    if not status_path.exists():
        return False
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(payload.get("success"))


def _task_contains_url(task: str) -> bool:
    return bool(re.search(r"https?://\S+", task))


def _github_repo_spec_from_task(task: str) -> GitHubRepoSpec | None:
    match = _GITHUB_REPO_URL_RE.search(task)
    if match is None:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    return GitHubRepoSpec(
        owner=owner,
        name=repo.removesuffix(".git"),
        clone_url=f"https://github.com/{owner}/{repo.removesuffix('.git')}.git",
    )


def _looks_like_git_repo(path: Path) -> bool:
    return path.is_dir() and ((path / ".git").exists() or (path / "HEAD").exists())


def _run_repo_materialization_command(
    *,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=stdout,
            stderr=stderr or f"timed out after {timeout_seconds} seconds",
        )


def _trim_repo_materialization_output(
    stdout: str, stderr: str, *, limit: int = 400
) -> str:
    detail = (stderr or stdout or "no output").strip()
    if len(detail) <= limit:
        return detail
    return f"{detail[:limit]}..."


def _remove_partial_repo(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _find_local_repo_for_github_task(
    *,
    spec: GitHubRepoSpec,
    node: TaskNode,
    workspace_root: Path,
) -> Path | None:
    seen: set[Path] = set()
    for root in _candidate_local_repo_search_roots(
        node=node, workspace_root=workspace_root
    ):
        if root in seen or not root.exists() or not root.is_dir():
            continue
        seen.add(root)
        direct = root / spec.name
        if _candidate_repo_matches_spec(direct, spec):
            return direct
        for candidate in _iter_candidate_repo_dirs(
            root, max_depth=_LOCAL_REPO_SEARCH_MAX_DEPTH
        ):
            if candidate == direct:
                continue
            if _candidate_repo_matches_spec(candidate, spec):
                return candidate
    return None


def _find_cached_code_repository(spec: GitHubRepoSpec) -> Path | None:
    if not _CODE_REPOSITORY_ROOT.exists() or not _CODE_REPOSITORY_ROOT.is_dir():
        return None
    direct_candidates = [
        _CODE_REPOSITORY_ROOT / spec.name,
        _CODE_REPOSITORY_ROOT / spec.owner / spec.name,
    ]
    for candidate in direct_candidates:
        if _candidate_repo_matches_spec(candidate, spec):
            return candidate
    for candidate in _iter_candidate_repo_dirs(_CODE_REPOSITORY_ROOT, max_depth=3):
        if _candidate_repo_matches_spec(candidate, spec):
            return candidate
    return None


def _candidate_local_repo_search_roots(
    *, node: TaskNode, workspace_root: Path
) -> list[Path]:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    task = str(metadata.get("task", ""))
    roots: list[Path] = []
    for match in _TASK_PATH_RE.finditer(task):
        candidate = Path(match.group(1).rstrip("。.,)"))
        roots.append(candidate if candidate.is_dir() else candidate.parent)
    roots.append(workspace_root)
    if workspace_root.parent != workspace_root:
        roots.append(workspace_root.parent)
    if workspace_root.parent.parent != workspace_root.parent:
        roots.append(workspace_root.parent.parent)
    roots.append(Path.cwd())
    return roots


def _iter_candidate_repo_dirs(root: Path, *, max_depth: int) -> list[Path]:
    candidates: list[Path] = []
    try:
        root_depth = len(root.resolve().parts)
    except OSError:
        root_depth = len(root.parts)
    for current_root, dirnames, _filenames in os.walk(root):
        current_path = Path(current_root)
        try:
            current_depth = len(current_path.resolve().parts) - root_depth
        except OSError:
            current_depth = len(current_path.parts) - root_depth
        if current_depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in {".git", ".venv", "__pycache__", "node_modules"}
        ]
        if current_path != root:
            candidates.append(current_path)
    return candidates


def _candidate_repo_matches_spec(candidate: Path, spec: GitHubRepoSpec) -> bool:
    if not _looks_like_git_repo(candidate):
        return False
    if candidate.name.casefold() == spec.name.casefold():
        return True
    remote = _read_git_origin_url(candidate)
    if remote is None:
        return False
    remote_spec = _github_repo_spec_from_url(remote)
    return remote_spec is not None and (
        remote_spec.owner.casefold() == spec.owner.casefold()
        and remote_spec.name.casefold() == spec.name.casefold()
    )


def _read_git_origin_url(repo_root: Path) -> str | None:
    completed = _run_repo_materialization_command(
        command=["git", "-C", str(repo_root), "remote", "get-url", "origin"],
        cwd=repo_root,
        timeout_seconds=30,
    )
    if completed.returncode != 0:
        return None
    remote = completed.stdout.strip()
    return remote or None


def _github_repo_spec_from_url(url: str) -> GitHubRepoSpec | None:
    match = _GITHUB_SSH_URL_RE.match(url.strip())
    if match is not None:
        owner = match.group("owner")
        repo = match.group("repo").removesuffix(".git")
        return GitHubRepoSpec(
            owner=owner,
            name=repo,
            clone_url=f"https://github.com/{owner}/{repo}.git",
        )
    parsed = urlparse(url)
    if parsed.netloc.casefold() != "github.com":
        return None
    path = parsed.path.strip("/")
    parts = path.split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    return GitHubRepoSpec(
        owner=owner,
        name=repo,
        clone_url=f"https://github.com/{owner}/{repo}.git",
    )


def _ensure_benchmark_analysis(
    *,
    repo: str,
    run_dir: Path,
) -> tuple[Path, Path]:
    analysis_json = run_dir / "cases" / repo / "analysis.json"
    analysis_md = run_dir / "cases" / repo / "analysis.md"
    if analysis_json.exists() and analysis_md.exists():
        return analysis_json, analysis_md
    case_dir = run_dir / "cases" / repo
    manifest_payload = _read_json_file(case_dir / "manifest.json")
    if not isinstance(manifest_payload, dict):
        return analysis_json, analysis_md
    status_payload = _read_json_file(case_dir / "run" / "status.json")
    if not isinstance(status_payload, dict):
        status_payload = _read_json_file(case_dir / "wdl" / "status.json")
    if not isinstance(status_payload, dict):
        return analysis_json, analysis_md
    result_manifest_path = case_dir / "run" / "result_manifest.json"
    result_manifest = _read_json_file(result_manifest_path)
    if not isinstance(result_manifest, dict):
        result_manifest = _write_benchmark_result_manifest(
            repo=repo,
            case_dir=case_dir,
            status_payload=status_payload,
        )
    _write_conservative_benchmark_analysis(
        repo=repo,
        case_dir=case_dir,
        manifest=manifest_payload,
        status_payload=status_payload,
        result_manifest=result_manifest,
    )
    return analysis_json, analysis_md


def _write_conservative_benchmark_analysis(
    *,
    repo: str,
    case_dir: Path,
    manifest: dict[str, object],
    status_payload: dict[str, object],
    result_manifest: dict[str, object],
) -> tuple[Path, Path]:
    analysis_json_path = case_dir / "analysis.json"
    analysis_md_path = case_dir / "analysis.md"
    artifact_paths: list[str] = []
    artifact_checksums: dict[str, str] = {}
    expected_outputs = result_manifest.get("expected_outputs", {})
    if isinstance(expected_outputs, dict):
        for payload in expected_outputs.values():
            if not isinstance(payload, dict):
                continue
            raw_path = payload.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = Path(raw_path.strip())
            if not path.exists() or not path.is_file():
                continue
            if str(path) not in artifact_paths:
                artifact_paths.append(str(path))
            checksum = _sha256_file(path)
            if checksum:
                artifact_checksums[path.name] = checksum
    raw_output_artifacts = status_payload.get("output_artifacts")
    if isinstance(raw_output_artifacts, list):
        for item in raw_output_artifacts:
            path = Path(str(item))
            if not path.exists() or not path.is_file():
                continue
            if str(path) not in artifact_paths:
                artifact_paths.append(str(path))
            checksum = _sha256_file(path)
            if checksum:
                artifact_checksums[path.name] = checksum
    real_contigs = any(Path(path).name == "contigs.fasta" for path in artifact_paths)
    payload = {
        "tool": repo,
        "dataset_key": str(manifest.get("dataset_key", "")).strip(),
        "status": "completed" if bool(status_payload.get("success")) else "failed",
        "family": str(manifest.get("family", "unknown")).strip() or "unknown",
        "artifact_paths": artifact_paths,
        "artifact_checksums": artifact_checksums,
        "metrics": {},
        "real_contigs_fasta": real_contigs,
        "summary": {
            "returncode": status_payload.get("returncode"),
            "artifact_count": len(artifact_paths),
            "failure_reason": _optional_str(status_payload.get("failure_reason")),
        },
    }
    _write_json(analysis_json_path, payload)
    lines = [
        "# Benchmark analysis",
        "",
        f"- Tool: `{repo}`",
        f"- Dataset: `{payload['dataset_key'] or 'unknown'}`",
        f"- Status: `{payload['status']}`",
        f"- Real `contigs.fasta` produced: **{'Yes' if real_contigs else 'No'}**",
    ]
    if status_payload.get("returncode") is not None:
        lines.append(f"- Return code: `{status_payload.get('returncode')}`")
    if artifact_paths:
        lines.append(f"- Artifact count: `{len(artifact_paths)}`")
    failure_reason = _optional_str(status_payload.get("failure_reason"))
    if failure_reason:
        lines.append(f"- Failure reason: {failure_reason}")
    analysis_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return analysis_json_path, analysis_md_path


def _write_benchmark_result_manifest(
    *,
    repo: str,
    case_dir: Path,
    status_payload: dict[str, object],
) -> dict[str, object]:
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    output_paths = _benchmark_expected_output_paths(
        repo=repo,
        case_dir=case_dir,
        status_payload=status_payload,
    )
    expected_outputs = {
        path.name: {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else None,
        }
        for path in output_paths
    }
    log_path = case_dir / "run" / "repo_native.log"
    output_log = next(
        (path for path in output_paths if path.name == "log" or path.suffix == ".log"),
        None,
    )
    payload = {
        "repo": repo,
        "dataset_key": manifest.get("dataset_key"),
        "status": "completed" if bool(status_payload.get("success")) else "failed",
        "success": bool(status_payload.get("success")),
        "returncode": status_payload.get("returncode"),
        "elapsed_seconds": status_payload.get("elapsed_seconds"),
        "command": status_payload.get("command"),
        "log_path": str(log_path),
        "output_dir": status_payload.get("output_dir"),
        "expected_outputs": expected_outputs,
        "lightweight_evidence": {
            "repo_native_log": {
                "path": str(log_path),
                "size_bytes": log_path.stat().st_size if log_path.exists() else None,
            },
            "log_tail_summary": _tail_nonempty_lines(output_log or log_path),
        },
        "failure_reason": status_payload.get("failure_reason"),
    }
    _write_json(case_dir / "run" / "result_manifest.json", payload)
    return payload


def _benchmark_expected_output_paths(
    *,
    repo: str,
    case_dir: Path,
    status_payload: dict[str, object],
) -> list[Path]:
    output_dir_raw = status_payload.get("output_dir")
    output_dir = (
        Path(output_dir_raw)
        if isinstance(output_dir_raw, str)
        else case_dir / "run" / "repo_native_output"
    )
    manifest_path = case_dir / "manifest.json"
    expected_outputs: list[str] = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        expected_outputs = [
            str(item)
            for item in manifest.get("expected_outputs", [])
            if isinstance(item, str) and item
        ]
    if expected_outputs:
        return [output_dir / name for name in expected_outputs]
    status_artifacts = [
        Path(item)
        for item in status_payload.get("output_artifacts", [])
        if isinstance(item, str) and item
    ]
    return status_artifacts


def _tail_nonempty_lines(path: Path, *, limit: int = 3) -> list[str]:
    if not path.exists():
        return []
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return lines[-limit:]


def _build_benchmark_result_record(
    *,
    repo: str,
    run_dir: Path,
    case_dir: Path,
    manifest: dict[str, object],
    status_payload: dict[str, object],
    result_manifest: dict[str, object],
    analysis_payload: dict[str, object] | None,
    analysis_markdown: str | None,
) -> dict[str, object]:
    workflow_signature = _benchmark_workflow_signature_from_manifest(manifest)
    input_signature = _benchmark_input_signature_from_manifest(manifest)
    selected_input_files = manifest.get("selected_input_files", {})
    selected_input_files_payload = (
        {str(key): str(value) for key, value in selected_input_files.items()}
        if isinstance(selected_input_files, dict)
        else {}
    )
    metrics = (
        analysis_payload.get("metrics", {})
        if isinstance(analysis_payload, dict)
        and isinstance(analysis_payload.get("metrics"), dict)
        else {}
    )
    canonical_parts = [
        repo,
        str(manifest.get("operator_id", "")).strip(),
        str(manifest.get("dataset_key", "")).strip(),
        str(manifest.get("wdl_workflow_name", "")).strip(),
        str(manifest.get("wdl_path", "")).strip(),
        " ".join(_benchmark_selected_input_names(selected_input_files_payload)),
        " ".join(str(key) for key in metrics.keys()),
        json.dumps(selected_input_files_payload, ensure_ascii=False, sort_keys=True),
    ]
    analysis_path = case_dir / "analysis.json"
    result_manifest_path = case_dir / "run" / "result_manifest.json"
    status_path = case_dir / "run" / "status.json"
    wdl_status_path = case_dir / "wdl" / "status.json"
    wdl_status_payload = (
        _read_json_file(wdl_status_path) if wdl_status_path.exists() else None
    )
    return {
        "record_id": f"benchmark-result:{repo}:{run_dir.name}",
        "repo": repo,
        "operator_id": str(manifest.get("operator_id", "")).strip(),
        "dataset_key": str(manifest.get("dataset_key", "")).strip(),
        "benchmark_root": str(manifest.get("source_case_dir", "")).strip(),
        "workflow_path": str(manifest.get("wdl_path", "")).strip(),
        "workflow_signature": workflow_signature,
        "inputs_json_path": str(manifest.get("inputs_path", "")).strip(),
        "input_signature": input_signature,
        "selected_input_files": selected_input_files_payload,
        "selected_input_names": _benchmark_selected_input_names(
            selected_input_files_payload
        ),
        "result_files": [
            str(path)
            for path in _benchmark_expected_output_paths(
                repo=repo,
                case_dir=case_dir,
                status_payload=status_payload,
            )
            if path.exists()
        ],
        "metrics": metrics,
        "success": bool(status_payload.get("success")),
        "returncode": status_payload.get("returncode"),
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "case_dir": str(case_dir),
        "status_path": str(status_path),
        "wdl_status_path": str(wdl_status_path),
        "result_manifest_path": str(result_manifest_path),
        "analysis_path": str(analysis_path),
        "status_payload": status_payload,
        "wdl_status_payload": wdl_status_payload
        if isinstance(wdl_status_payload, dict)
        else {},
        "result_manifest": result_manifest,
        "analysis_payload": analysis_payload or {},
        "analysis_markdown": analysis_markdown or "",
        "canonical_text": "\n".join(part for part in canonical_parts if part),
        "updated_at": _utc_now(),
    }


def _materialize_benchmark_result_record(
    *,
    repo: str,
    run_dir: Path,
    case_dir: Path,
    manifest: dict[str, object],
    status_payload: dict[str, object],
    result_manifest: dict[str, object],
) -> Path | None:
    return _materialize_benchmark_result_record_to_store(
        repo=repo,
        run_dir=run_dir,
        case_dir=case_dir,
        manifest=manifest,
        status_payload=status_payload,
        result_manifest=result_manifest,
        store_root=_benchmark_result_store_root_for_run_dir(run_dir),
    )


def _materialize_benchmark_result_record_to_store(
    *,
    repo: str,
    run_dir: Path,
    case_dir: Path,
    manifest: dict[str, object],
    status_payload: dict[str, object],
    result_manifest: dict[str, object],
    store_root: Path,
) -> Path | None:
    analysis_path = case_dir / "analysis.json"
    analysis_md_path = case_dir / "analysis.md"
    analysis_payload = (
        _read_json_file(analysis_path) if analysis_path.exists() else None
    )
    analysis_markdown = (
        analysis_md_path.read_text(encoding="utf-8")
        if analysis_md_path.exists()
        else ""
    )
    store = BenchmarkResultStore(_benchmark_result_store_root_for_run_dir(run_dir))
    record = _build_benchmark_result_record(
        repo=repo,
        run_dir=run_dir,
        case_dir=case_dir,
        manifest=manifest,
        status_payload=status_payload,
        result_manifest=result_manifest,
        analysis_payload=analysis_payload
        if isinstance(analysis_payload, dict)
        else None,
        analysis_markdown=analysis_markdown,
    )
    try:
        return BenchmarkResultStore(store_root).write_record(record)
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error):
        return None


def _try_reuse_benchmark_result_record(
    *,
    repo: str,
    task: str,
    workspace_root: Path,
    run_dir: Path,
    case_dir: Path,
    manifest: dict[str, object],
) -> WorkerResult | None:
    workflow_signature = _benchmark_workflow_signature_from_manifest(manifest)
    input_signature = _benchmark_input_signature_from_manifest(manifest)
    dataset_key = str(manifest.get("dataset_key", "")).strip()
    operator_id = str(manifest.get("operator_id", "")).strip()
    query = _benchmark_result_query(repo=repo, task=task, manifest=manifest)
    _ensure_workspace_benchmark_history_backfilled(workspace_root)
    filters = BenchmarkResultSearchFilter(
        query=query,
        repo=repo,
        operator_id=operator_id or None,
        success_only=True,
        limit=8,
    )
    for store_root in _candidate_benchmark_result_store_roots(workspace_root):
        try:
            store = BenchmarkResultStore(store_root)
            candidates = store.search_records(filters)
        except sqlite3.Error:
            continue
        for candidate in candidates:
            if not _benchmark_history_candidate_matches(
                candidate=candidate,
                workflow_signature=workflow_signature,
                input_signature=input_signature,
                dataset_key=dataset_key,
                current_run_id=run_dir.name,
            ):
                continue
            record_path_raw = candidate.get("record_path")
            if not isinstance(record_path_raw, str) or not record_path_raw.strip():
                continue
            record_path = Path(record_path_raw)
            if not record_path.exists():
                continue
            record_payload = _read_json_file(record_path)
            if not isinstance(record_payload, dict):
                continue
            result = _materialize_reused_benchmark_result(
                repo=repo,
                run_dir=run_dir,
                case_dir=case_dir,
                record_payload=record_payload,
            )
            if result is not None:
                return result
    return None


def _benchmark_history_candidate_matches(
    *,
    candidate: dict[str, object],
    workflow_signature: str,
    input_signature: str,
    dataset_key: str,
    current_run_id: str,
) -> bool:
    if str(candidate.get("run_id", "")).strip() == current_run_id:
        return False
    if not bool(candidate.get("success")):
        return False
    candidate_workflow_signature = str(candidate.get("workflow_signature", "")).strip()
    if workflow_signature and candidate_workflow_signature != workflow_signature:
        return False
    candidate_input_signature = str(candidate.get("input_signature", "")).strip()
    if input_signature and candidate_input_signature == input_signature:
        return True
    candidate_dataset_key = str(candidate.get("dataset_key", "")).strip()
    return bool(dataset_key) and candidate_dataset_key == dataset_key


def _materialize_reused_benchmark_result(
    *,
    repo: str,
    run_dir: Path,
    case_dir: Path,
    record_payload: dict[str, object],
) -> WorkerResult | None:
    result_manifest = record_payload.get("result_manifest")
    status_payload = record_payload.get("status_payload")
    if not isinstance(result_manifest, dict) or not isinstance(status_payload, dict):
        return None
    result_files = [
        str(item).strip()
        for item in record_payload.get("result_files", [])
        if isinstance(item, str) and str(item).strip()
    ]
    if not result_files or not all(Path(path).exists() for path in result_files):
        return None

    analysis_payload = record_payload.get("analysis_payload")
    analysis_markdown = (
        str(record_payload.get("analysis_markdown", ""))
        if record_payload.get("analysis_markdown") is not None
        else ""
    )
    status_path = case_dir / "run" / "status.json"
    result_manifest_path = case_dir / "run" / "result_manifest.json"
    analysis_path = case_dir / "analysis.json"
    analysis_md_path = case_dir / "analysis.md"
    wdl_status_path = case_dir / "wdl" / "status.json"
    reused_record_path = case_dir / "run" / "reused_result_record.json"

    reused_status_payload = {
        **status_payload,
        "attempted": True,
        "completed": True,
        "success": True,
        "command": ["reuse-history", repo],
        "execution_mode": "history_reuse",
        "reused_from_record_path": str(record_payload.get("record_path", "")),
        "reused_from_run_dir": str(record_payload.get("run_dir", "")),
        "output_artifacts": result_files,
        "finished_at": _utc_now(),
    }
    _write_json(status_path, reused_status_payload)
    _write_json(result_manifest_path, result_manifest)
    if isinstance(analysis_payload, dict):
        _write_json(analysis_path, analysis_payload)
    if analysis_markdown:
        analysis_md_path.write_text(analysis_markdown, encoding="utf-8")
    if isinstance(record_payload.get("wdl_status_payload"), dict):
        _write_json(wdl_status_path, record_payload.get("wdl_status_payload"))
    _write_json(
        reused_record_path,
        {
            "repo": repo,
            "record_path": str(record_payload.get("record_path", "")),
            "run_dir": str(record_payload.get("run_dir", "")),
            "reused_at": _utc_now(),
        },
    )

    artifacts = [
        str(status_path),
        str(result_manifest_path),
        str(reused_record_path),
        *result_files,
    ]
    if analysis_path.exists():
        artifacts.append(str(analysis_path))
    if analysis_md_path.exists():
        artifacts.append(str(analysis_md_path))
    if wdl_status_path.exists():
        artifacts.append(str(wdl_status_path))
    evidence = [
        str(case_dir / "execution_ready.json"),
        str(case_dir / "dataset_manifest.json"),
        str(status_path),
        str(result_manifest_path),
        str(reused_record_path),
    ]
    source_run_dir = str(record_payload.get("run_dir", "")).strip() or "historical run"
    return WorkerResult(
        status="completed",
        summary=f"Reused previously computed benchmark result for {repo} from {source_run_dir}.",
        artifacts=artifacts,
        evidence=evidence,
        next_action_hint="summary",
    )


async def _run_worker_and_capture(
    *,
    node: TaskNode,
    graph_round: int,
    run_dir: Path,
    worker_runner,
) -> WorkerResult:
    node = _augment_node_with_runtime_context(
        node=node, graph_round=graph_round, run_dir=run_dir
    )
    started_at = datetime.now(UTC)
    _append_tool_activity_event(
        run_dir=run_dir,
        event={
            "event": "node_started",
            "round_index": graph_round,
            "node_id": node.node_id,
        },
    )
    _append_raw_worker_trace(
        node=node,
        event={
            "event": "node_started",
            "round_index": graph_round,
            "node_id": node.node_id,
            "started_at": started_at.isoformat(),
            "title": node.title,
            "objective": node.objective,
            "capability_bundles": list(node.capability_bundles),
        },
    )
    _emit_supervisor_event(
        kind="node_started",
        round_index=graph_round,
        node_id=node.node_id,
        title=node.title,
        objective=node.objective,
        capability_bundles=list(node.capability_bundles),
    )

    async def _heartbeat_until_done(task: asyncio.Task[WorkerResult]) -> None:
        interval_seconds = _worker_heartbeat_seconds()
        if interval_seconds is None:
            return
        started_at = asyncio.get_running_loop().time()
        heartbeat_count = 0
        while not task.done():
            await asyncio.sleep(interval_seconds)
            if task.done():
                break
            heartbeat_count += 1
            elapsed_seconds = round(asyncio.get_running_loop().time() - started_at, 3)
            event = {
                "event": "node_heartbeat",
                "round_index": graph_round,
                "node_id": node.node_id,
                "heartbeat_count": heartbeat_count,
                "elapsed_seconds": elapsed_seconds,
            }
            try:
                _append_tool_activity_event(run_dir=run_dir, event=event)
            except OSError:
                return
            _emit_supervisor_event(
                kind="node_heartbeat",
                round_index=graph_round,
                node_id=node.node_id,
                title=node.title,
                heartbeat_count=heartbeat_count,
                elapsed_seconds=elapsed_seconds,
            )

    worker_task = asyncio.create_task(
        worker_runner(node),
        name=f"supervisor-worker:{graph_round}:{node.node_id}",
    )
    heartbeat_task = asyncio.create_task(
        _heartbeat_until_done(worker_task),
        name=f"supervisor-heartbeat:{graph_round}:{node.node_id}",
    )
    try:
        timeout_seconds = _worker_timeout_seconds(node)
        result = await (
            asyncio.wait_for(worker_task, timeout=timeout_seconds)
            if timeout_seconds is not None
            else worker_task
        )
    except GraphBubbleUp:
        _append_tool_activity_event(
            run_dir=run_dir,
            event={
                "event": "node_interrupted",
                "round_index": graph_round,
                "node_id": node.node_id,
            },
        )
        _emit_supervisor_event(
            kind="node_interrupted",
            round_index=graph_round,
            node_id=node.node_id,
            title=node.title,
        )
        raise
    except TimeoutError:
        timeout_seconds = _worker_timeout_seconds(node)
        timeout_display = (
            f"{timeout_seconds} seconds"
            if timeout_seconds
            else "the configured timeout"
        )
        result = WorkerResult(
            status="partial",
            summary=f"{node.node_id} timed out after {timeout_display}.",
            failure_reason="worker_timeout",
            next_action_hint=(
                "Continue with available evidence and explicitly mark this node's evidence as incomplete."
            ),
        )
        _append_tool_activity_event(
            run_dir=run_dir,
            event={
                "event": "node_timeout",
                "round_index": graph_round,
                "node_id": node.node_id,
                "timeout_seconds": timeout_seconds,
            },
        )
        _emit_supervisor_event(
            kind="node_timeout",
            round_index=graph_round,
            node_id=node.node_id,
            title=node.title,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _append_tool_activity_event(
            run_dir=run_dir,
            event={
                "event": "node_exception",
                "round_index": graph_round,
                "node_id": node.node_id,
                "error": error,
            },
        )
        _emit_supervisor_event(
            kind="node_exception",
            round_index=graph_round,
            node_id=node.node_id,
            title=node.title,
            error=error,
        )
        if _is_report_evidence_lane_node(node):
            result = WorkerResult(
                status="partial",
                summary=(
                    f"{node.node_id} stopped after a worker/tool exception; "
                    "continue composition with available lane traces and mark this lane incomplete."
                ),
                artifacts=_report_partial_exception_artifacts(
                    run_dir=run_dir, node=node
                ),
                evidence=[
                    f"report evidence lane exception: {error}",
                    f"raw trace: {run_dir / 'raw_worker_traces' / f'{node.node_id}.jsonl'}",
                ],
                failure_reason=f"worker_exception:{error}",
                next_action_hint=(
                    "Compose from completed lanes and explicitly state this lane's evidence gap."
                ),
            )
        else:
            raise
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
    result = _postprocess_worker_result(
        node=node,
        result=result,
        run_dir=run_dir,
    )
    payload = {
        "round_index": graph_round,
        "node": node.to_dict(),
        "result": result.to_dict(),
    }
    _write_json(run_dir / "worker_outputs" / f"{node.node_id}.json", payload)
    _write_json(run_dir / "node_traces" / f"{node.node_id}.json", payload)
    _append_tool_activity_event(
        run_dir=run_dir,
        event={
            "event": "node_finished",
            "round_index": graph_round,
            "node_id": node.node_id,
            "status": result.status,
        },
    )
    finished_at = datetime.now(UTC)
    _append_raw_worker_trace(
        node=node,
        event={
            "event": "node_finished",
            "round_index": graph_round,
            "node_id": node.node_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
            "status": result.status,
            "source_urls": _extract_source_urls_from_object(result.to_dict()),
            "worker_result": result.to_dict(),
        },
    )
    _emit_supervisor_event(
        kind="node_finished",
        round_index=graph_round,
        node_id=node.node_id,
        title=node.title,
        status=result.status,
        summary=result.summary,
        failure_reason=result.failure_reason,
        next_action_hint=result.next_action_hint,
        artifacts=list(result.artifacts),
        evidence=list(result.evidence),
    )
    return result


def _is_report_evidence_lane_node(node: TaskNode) -> bool:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if str(metadata.get("task_type", "")).strip() != "report":
        return False
    node_id = node.node_id.lower()
    if node_id in {"init_report", "compose_report", "summarize", "final_response"}:
        return False
    if node_id.startswith("retry_"):
        node_id = node_id.removeprefix("retry_")
    report_lane_base = str(metadata.get("report_lane_base", "")).strip()
    return (
        bool(report_lane_base)
        or node_id.endswith("_lane")
        or "_lane_" in node_id
        or node_id.startswith(
            (
                "monitoring_lane",
                "existing_data_lane",
                "computed_data_lane",
                "local_data_lane",
                "literature_lane",
            )
        )
    )


def _report_partial_exception_artifacts(*, run_dir: Path, node: TaskNode) -> list[str]:
    candidates = [
        run_dir / "raw_worker_traces" / f"{node.node_id}.jsonl",
        run_dir / "tool_activity.jsonl",
    ]
    artifacts = [str(path) for path in candidates if path.exists()]
    node_dir_names = {
        node.node_id,
        node.node_id.removeprefix("retry_"),
    }
    for base_dir in (
        run_dir / "evidence_layers",
        run_dir / "artifacts",
        run_dir / "lanes",
    ):
        if not base_dir.exists():
            continue
        for path in base_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(name in str(path.relative_to(base_dir)) for name in node_dir_names):
                artifacts.append(str(path))
    return list(dict.fromkeys(artifacts))


def _worker_timeout_seconds(node: TaskNode) -> float | None:
    """Return a worker timeout for node types that should not block a graph forever."""

    if not _is_report_worker_node(node):
        return None
    raw_timeout = (get_env(SUPERVISOR_REPORT_NODE_TIMEOUT_ENV, "") or "").strip()
    if raw_timeout:
        try:
            timeout = float(raw_timeout)
        except ValueError:
            timeout = float(SUPERVISOR_REPORT_NODE_TIMEOUT_SECONDS)
        if timeout <= 0:
            return None
        return timeout
    return float(SUPERVISOR_REPORT_NODE_TIMEOUT_SECONDS)


def _worker_heartbeat_seconds() -> float | None:
    raw_interval = (get_env(SUPERVISOR_WORKER_HEARTBEAT_ENV, "") or "").strip()
    if raw_interval:
        try:
            interval = float(raw_interval)
        except ValueError:
            interval = float(SUPERVISOR_WORKER_HEARTBEAT_SECONDS)
    else:
        interval = float(SUPERVISOR_WORKER_HEARTBEAT_SECONDS)
    if interval <= 0:
        return None
    return interval


def _is_report_worker_node(node: TaskNode) -> bool:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if str(metadata.get("task_type", "")).strip() == "report":
        return True
    normalized = node.node_id.lower()
    return "report" in normalized or normalized.endswith("_lane")


def _augment_node_with_runtime_context(
    *,
    node: TaskNode,
    graph_round: int,
    run_dir: Path,
) -> TaskNode:
    """Attach generic runtime context for downstream workers."""

    prior_worker_outputs = sorted(
        str(path)
        for path in (run_dir / "worker_outputs").glob("*.json")
        if path.is_file()
    )
    prior_node_traces = sorted(
        str(path) for path in (run_dir / "node_traces").glob("*.json") if path.is_file()
    )
    run_dir_artifacts = sorted(
        str(path)
        for path in run_dir.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".txt", ".log"}
    )
    prior_worker_output_payloads: dict[str, object] = {}
    for path in (run_dir / "worker_outputs").glob("*.json"):
        if not path.is_file():
            continue
        try:
            prior_worker_output_payloads[path.name] = _summarize_worker_output_payload(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, OSError):
            continue
    runtime_metadata = {
        "graph_round": graph_round,
        "run_dir": str(run_dir),
        "prior_worker_outputs": _compact_path_list(prior_worker_outputs),
        "prior_node_traces": _compact_path_list(prior_node_traces),
        "run_dir_artifacts": _compact_path_list(run_dir_artifacts),
        "prior_worker_output_payloads": prior_worker_output_payloads,
    }
    return TaskNode(
        node_id=node.node_id,
        title=node.title,
        objective=node.objective,
        capability_bundles=list(node.capability_bundles),
        metadata={**node.metadata, **runtime_metadata},
    )


def _build_worker_prompt(*, node: TaskNode, workspace_root: Path) -> str:
    bundles = ", ".join(node.capability_bundles)
    now_utc = datetime.now(UTC)
    local_now = now_utc.astimezone()
    capability_summaries, allowed_tools, implementation_kinds = describe_capabilities(
        node.capability_bundles
    )
    metadata_hint = ""
    if node.metadata:
        metadata_hint = _compact_metadata_hint(node.metadata)
    guidance_lines = node_guidance_lines(node.node_id)
    guidance_ids = (
        node.metadata.get("guidance_ids", []) if isinstance(node.metadata, dict) else []
    )
    if (
        isinstance(node.metadata, dict)
        and node.metadata.get("task_type") == "benchmark"
        and node.node_id not in {"register", "summarize"}
    ):
        guidance_lines.extend(node_guidance_lines("benchmark_case"))
    if isinstance(guidance_ids, list):
        guidance_lines.extend(
            family_guidance_lines([str(item) for item in guidance_ids])
        )
        if isinstance(node.metadata, dict):
            guidance_lines.extend(
                generic_experience_guidance_lines(
                    task=str(node.metadata.get("task", "")),
                    guidance_ids=[str(item) for item in guidance_ids],
                )
            )
    if "report" in node.node_id or "lane" in node.node_id:
        guidance_lines.append(
            "For report-oriented nodes, prefer writing concrete report artifacts into the workspace such as request notes, lane notes, evidence summaries, or final_report.md when relevant."
        )
        guidance_lines.append(
            "For report-oriented nodes, record the main evidence sources used, their dates or freshness when relevant, and whether they directly support the claim or only provide proxy context."
        )
    if node.node_id == "init_generic":
        guidance_lines.extend(
            [
                "This node plans the next generic graph; do not answer the user fully in this node.",
                "Use the user's request to choose a flexible graph shape. You may use examples such as direct answer, code inspect/fix/verify, data inspect/analyze/recommend, migration planning, or research/evidence judgment, but do not force a template.",
                "Research and evidence-judgment questions are the main generic scenario. For simple questions use one synthesis node; for harder ones create sequential or parallel evidence/source/analysis lanes as needed.",
                "If the generic task needs prediction, simulation, scoring, metric calculation, or any computed evidence, plan an explicit worker that searches operator_store for candidate operators, selects a compatible local dataset/input bundle, runs the concrete WDL/Docker/entrypoint path when available, and returns the computed artifact as evidence.",
                "Give that computation worker capability_bundles such as db_access, operator_filter, data_filter, metric_compute, validate, and wdl_run or docker_build_run when the runtime path requires them.",
                "Put the next-round graph in spawned_subgraph with keys nodes and edges. Each node must include node_id, title, objective, and capability_bundles. Each edge must include source and target.",
                "Use only these capability_bundles: repo_fetch, docker_build_run, wdl_run, data_filter, operator_filter, metric_compute, summarize, validate, plan, task_manage, web_search, web_fetch, db_access, api_call.",
                "Always include a final summarize node unless the graph has exactly one direct synthesis node followed by summarize.",
            ]
        )
    if node.node_id == "init_report":
        guidance_lines.extend(
            [
                "This node plans the dynamic report evidence graph; do not collect lane evidence or draft the report body here.",
                "Decide each possible lane independently. Include a lane only when it has a concrete role in satisfying the user's report request.",
                "Allowed report lane base types are monitoring_lane, existing_data_lane, computed_data_lane, and literature_lane.",
                "monitoring_lane is for official surveillance, operational monitoring, dashboards, alerts, or latest status evidence.",
                "existing_data_lane is for querying already materialized local databases, registries, APIs, dataset_store records, cached artifacts, and history records. It must not run new operators.",
                "computed_data_lane is for cases where the report needs a value that does not already exist and should be produced by selecting a local operator plus compatible dataset/input bundle and running it.",
                "literature_lane is for literature, preprints, technical reports, or primary-source web material.",
                "You may create 0-3 nodes for each lane base type and at most 6 evidence-lane nodes total. Use multiple nodes of one base type only for genuinely independent branches, such as different pathogens, datasets, regions, or metrics.",
                "The report contract artifact must explicitly declare the report shape with a field such as shape_archetype, report_archetype, expected_report_shape, required_sections_outline, or organizing_logic.",
                "Put the selected next-round graph in spawned_subgraph with keys nodes and edges. Each node must include node_id, title, objective, and capability_bundles; optional lane_type may name the lane base type.",
                "Do not include init_report in spawned_subgraph. Include compose_report and summarize only if useful; the runtime will add them when missing.",
                "Use node_id values that start with one of the lane base types, for example monitoring_lane, existing_data_lane_2, computed_data_lane_growth, or literature_lane_vaccine.",
                "Use only these capability_bundles: web_search, web_fetch, db_access, api_call, data_filter, operator_filter, metric_compute, wdl_run, docker_build_run, summarize, validate.",
            ]
        )
    if node.node_id == "compose_report":
        run_dir_hint = str(node.metadata.get("run_dir", "")).strip() or "<run_dir>"
        guidance_lines.extend(
            [
                "This node must create the final report artifact, not only summarize what it would write.",
                f"Write the full user-facing Markdown report to `{run_dir_hint}/composed_report/final_report.md` before returning.",
                "Return JSON only after the artifact exists; include that final_report.md path in artifacts and mention it in summary.",
                "Do not finish with an empty response, a placeholder such as `Worker completed.`, or a JSON result that has no final report artifact.",
                "The report artifact must use valid Markdown spacing: `# 标题`, `## 一、章节`, `### 1.1 小节`, `1. 条目`, and `- 条目`.",
                "Keep the report paragraph-led. Use bullets only for compact takeaways, recommendations, enumerations, or sources.",
            ]
        )
    if node.node_id.startswith("summarize") or node.node_id == "summarize":
        guidance_lines.extend(
            [
                "This is a synthesis node. Prefer using prior worker outputs and traces rather than opening new exploratory work.",
                "Do not start fresh evidence collection, broad repo scans, or unrelated validation unless a hard blocker in prior outputs requires one tiny targeted check.",
                "Stop as soon as you can produce the requested summary or final answer from existing worker results.",
            ]
        )
    if _looks_like_user_delivery_node(node.node_id):
        guidance_lines.append(
            "If this node prepares the final user-facing answer, put that answer itself in summary; put process notes, worker contributions, blockers, and evidence details in evidence or next_action_hint instead."
        )
    if node.node_id == "final_response":
        guidance_lines.extend(
            [
                "You are the final chat-facing answer editor. Write the answer the user should see, not an execution log.",
                "Use only the source material already gathered by supervisor and workers. Do not invent files, commands, evidence, test results, or completion status.",
                (
                    "Prefer Chinese for user-facing prose when the original task is Chinese "
                    "or does not explicitly request another language. Only use another "
                    "language when the user explicitly asks for it or an exact-output "
                    "constraint requires it."
                ),
                (
                    "Never return the raw Supervisor Summary, round list, node list, JSON "
                    "payload, or other internal diagnostics as the final chat response. "
                    "Rewrite them into natural language."
                ),
                "Lead with useful information that was successfully obtained. Mention unfinished, failed, or blocked work only when it materially changes what the user can rely on.",
                "For report, risk assessment, monitoring, or judgment-style answers, include a brief evidence-source explanation unless the user's requested format forbids it. Name the source categories and preserve direct-vs-inferred evidence distinctions.",
                "For judgment-style answers, end the final response with a short section titled '判断轨迹（可审计摘要）'. This section must expose the auditable reasoning path, not private chain-of-thought: list the evidence checked, comparison rule, key inference, and uncertainty or gaps so a reviewer can spot likely false positives.",
                "When something is partial, phrase it calmly and briefly; do not over-emphasize internal node names, rounds, worker contributions, or supervisor diagnostics.",
                "Respect strict output constraints from the original user request. If the user asked for an exact short answer, put only that answer in summary.",
                "When mentioning local files or artifacts in the final answer, do not expose absolute filesystem paths. For files inside the current run directory, use run-relative paths such as `cases/...`; for other files under the project, use project-relative paths such as `workspace/...`.",
                "For benchmark answers, explicitly state which dataset or input bundle was actually used. If no canonical dataset key was resolved, say that clearly and name the real per-tool input set or benchmark-root case inputs instead.",
                "Return JSON only; the summary field must contain the final natural-language response itself.",
            ]
        )
        if (
            isinstance(node.metadata, dict)
            and str(node.metadata.get("task_type", "")).strip() == "report"
        ):
            guidance_lines.extend(
                [
                    "For report task final responses, preserve the composed report as a structured Markdown deliverable instead of compressing it into a chat summary.",
                    "Keep the report shape chosen by composition unless the user requested another format; do not force a default heading checklist at the final-response step.",
                    "Use one # title, ## section headings, and ### subsections only where they improve readability.",
                    "Keep formal reports paragraph-led: each substantive section should use cohesive paragraphs as the main body, not one-sentence bullet notes.",
                    "Use bullets or numbered lists only for short takeaways, recommendations, risk dimensions, compact enumerations, or source lists; do not convert the report body into a note-style outline.",
                    "Markdown syntax must be valid: put one space after heading markers and after ordered/unordered list markers; never write `#标题`, `###1.1标题`, `1.结论`, or `-证据`.",
                    "Write in the same language as the user's report request unless the user explicitly asked otherwise.",
                    "Do not expose worker names, internal node names, or orchestration diagnostics in the report body; mention local artifact paths only in the evidence appendix when useful for auditability.",
                    "Keep citations or source references consistent. If the composed report used numbered sources, preserve the numbering and include the source list.",
                    "If the report includes recommendations, make each recommendation traceable to a finding, source, artifact, or explicit uncertainty already present in the supervisor material.",
                    "If prior material is incomplete, keep the relevant report section and state the evidence gap briefly instead of deleting the section.",
                ]
            )
    guidance_block = "\n".join(f"- {line}" for line in guidance_lines)
    capability_block = "\n".join(capability_summaries)
    implementation_block = "\n".join(implementation_kinds)
    allowed_tools_block = ", ".join(allowed_tools)
    local_computation_block = _local_computation_context_material(
        node=node,
        workspace_root=workspace_root,
    )
    return (
        "You are a generic worker node executor.\n"
        "Execute only the assigned node.\n"
        "Once the node's minimum required outputs exist, stop immediately and return the structured JSON result.\n"
        "Do not continue exploring after the node has enough information to hand control back to supervisor.\n"
        f"Workspace root: {workspace_root}\n"
        f"Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"Current local time: {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        "If the node depends on latest or recent information, use these timestamps as the time anchor, verify freshness explicitly, and prefer absolute dates in artifacts.\n"
        f"Node ID: {node.node_id}\n"
        f"Objective: {node.objective}\n"
        f"Original task: {node.metadata.get('task', '')}\n"
        f"Task paths: {node.metadata.get('task_paths', [])}\n"
        f"Run directory: {node.metadata.get('run_dir', '')}\n"
        f"Prior worker outputs: {_compact_path_list(list(node.metadata.get('prior_worker_outputs', []) or []))}\n"
        f"Prior node traces: {_compact_path_list(list(node.metadata.get('prior_node_traces', []) or []))}\n"
        f"Run-dir artifacts: {_compact_path_list(list(node.metadata.get('run_dir_artifacts', []) or []))}\n"
        f"Prior worker output payloads: {json.dumps(node.metadata.get('prior_worker_output_payloads', {}), ensure_ascii=False)}\n"
        f"Allowed capability bundles: {bundles}\n"
        f"Capability details:\n{capability_block}\n"
        f"Implementation style:\n{implementation_block}\n"
        f"Preferred tool surface: {allowed_tools_block}\n"
        f"{metadata_hint}\n"
        f"{_final_response_source_material(node)}"
        f"{local_computation_block}"
        f"Node guidance:\n{guidance_block}\n\n"
        "Return JSON only with keys: "
        "status, summary, artifacts, evidence, next_action_hint, failure_reason, spawned_subgraph.\n"
        "status must be one of completed, blocked, failed, partial."
    )


def _local_computation_context_material(*, node: TaskNode, workspace_root: Path) -> str:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    task_type = str(metadata.get("task_type", "")).strip()
    node_id = node.node_id.lower()
    report_lane_base = str(metadata.get("report_lane_base", "")).strip().lower()
    is_report_existing_data = task_type == "report" and (
        "existing_data" in node_id or report_lane_base == "existing_data_lane"
    )
    is_report_computed_data = task_type == "report" and (
        "computed_data" in node_id
        or "local_data" in node_id
        or report_lane_base == "computed_data_lane"
    )
    is_report_local_data = is_report_existing_data or is_report_computed_data
    is_generic_evidence_or_compute = task_type == "generic" and (
        node_id in {"worker_context", "worker_solution"}
        or "data" in node_id
        or "compute" in node_id
        or "prediction" in node_id
        or "forecast" in node_id
        or any(
            bundle in set(node.capability_bundles)
            for bundle in (
                "db_access",
                "operator_filter",
                "metric_compute",
                "data_filter",
            )
        )
    )
    if not (is_report_local_data or is_generic_evidence_or_compute):
        return ""

    task = str(metadata.get("task", "")).strip()
    _ensure_workspace_benchmark_history_backfilled(workspace_root)
    history_roots = _candidate_benchmark_result_store_roots(workspace_root)
    operator_roots = _candidate_operator_store_roots(workspace_root)
    dataset_roots = _candidate_dataset_store_roots(workspace_root)
    if is_report_existing_data:
        header = "Report existing local data source context:"
        footer = "End report existing local data source context."
    elif is_report_computed_data:
        header = "Report computed local data source context:"
        footer = "End report computed local data source context."
    else:
        header = "Local computation context:"
        footer = "End local computation context."
    if not history_roots and not operator_roots and not dataset_roots:
        missing_local_lines = [
            f"{header}",
            "- Local report data is split into existing_data and computed_data lanes.",
        ]
        if is_report_existing_data:
            missing_local_lines.extend(
                [
                    "- This existing_data lane should query only already materialized local databases, registries, APIs, cached artifacts, dataset_store records, and history records.",
                    "- Do not run operators from this lane. If no relevant existing local data is available, return an explicit null-result statement.",
                ]
            )
        else:
            missing_local_lines.extend(
                [
                    "- This computed_data lane should first verify that existing data is insufficient, then look for a compatible operator and dataset/input bundle.",
                    "- No operator_store or dataset_store directory was found under the current workspace or configured shared stores.",
                    "- If the task needs prediction, simulation, scoring, metric calculation, or other computed evidence, explicitly report that no local operator/data library was available.",
                ]
            )
        missing_local_lines.extend(
            [
                "- No local history store was found either; this is optional.",
                f"{footer}",
            ]
        )
        if is_report_local_data:
            return "\n".join(missing_local_lines) + "\n"
        return (
            f"{header}\n"
            "- Local data lane split: existing_data comes from local databases, registries, APIs, cached run artifacts, dataset_store records, or history records; computed_data must be produced by selecting a local operator plus a compatible dataset/input bundle and running it.\n"
            "- Decision order: first judge whether existing_data is already sufficient for this node; only if a concrete evidence gap remains should you treat it as computed_data.\n"
            "- No operator_store or dataset_store directory was found under the current workspace or configured shared stores.\n"
            "- No local history store was found either; this is optional and should not block operator-store computation.\n"
            "- If the task needs prediction, simulation, scoring, metric calculation, or other computed evidence, explicitly report that no local operator/data library was available.\n"
            f"{footer}\n"
        )

    rows: list[dict[str, object]] = []
    for root in history_roots:
        try:
            store = BenchmarkResultStore(root)
            store_rows = store.search_records(
                BenchmarkResultSearchFilter(success_only=False, limit=30)
            )
        except Exception:
            store_rows = []
        for row in store_rows:
            row_with_root = dict(row)
            row_with_root["store_root"] = str(root)
            rows.append(row_with_root)

    ranked = _rank_report_benchmark_history_rows(task=task, rows=rows)
    operator_candidates = _rank_local_operator_candidates(
        task=task,
        workspace_root=workspace_root,
        limit=8,
    )
    dataset_store_candidates = _rank_local_dataset_store_candidates(
        task=task,
        workspace_root=workspace_root,
        limit=10,
    )
    dataset_candidates = _local_dataset_candidates(
        history_rows=ranked,
        operator_candidates=operator_candidates,
        dataset_store_candidates=dataset_store_candidates,
    )
    lines = [
        header,
        "- Local report data is split into separate lanes:",
        "  - existing_data: already materialized local database rows, registries, APIs, cached run artifacts, dataset_store records, and optional history records.",
        "  - computed_data: values that do not exist yet and must be produced by retrieving a compatible local operator and dataset_store/input bundle, running the operator, then citing its new result artifacts.",
        "- Decision order:",
        "  1. First judge whether existing_data already answers the local-data need well enough.",
        "  2. Only if a concrete evidence gap remains, decide whether computed_data is actually required.",
        "  3. Only if new computation is truly required, search for a compatible operator and dataset/input bundle.",
        "- Treat benchmark_comparison_history_store records as optional existing_data only when they are directly relevant; do not let history lookup distract from selecting and running a needed local operator.",
        "- Keep local existing/computed evidence distinct from external web/literature evidence and cite record_path/run_id/operator_path/dataset/input paths when used.",
        f"- benchmark_comparison_history_store_roots: {', '.join(str(root) for root in history_roots) or 'none'}",
        f"- operator_store_roots: {', '.join(str(root) for root in operator_roots) or 'none'}",
        f"- dataset_store_roots: {', '.join(str(root) for root in dataset_roots) or 'none'}",
    ]
    if is_report_existing_data:
        lines.extend(
            [
                "- This is an existing_data lane: query and summarize only already available local records or APIs.",
                "- Do not run operators from this lane. If existing_data is insufficient for a computed claim, record the gap for a computed_data lane or composition.",
            ]
        )
    elif is_report_computed_data or is_generic_evidence_or_compute:
        lines.extend(
            [
                "- Prioritize operator_store records as the local operator library for prediction, simulation, scoring, metric calculation, benchmark reruns, or other computed evidence.",
                "- Use dataset_store records as the preferred local dataset/input-bundle library before falling back to operator input hints or old benchmark history.",
                "- Do not run an operator by default just because operator_store candidates exist.",
                "- When computed_data is needed, first explain why existing_data is insufficient, then choose the operator and dataset_store/input bundle, inspect the operator runtime fields, run the concrete WDL/Docker/entrypoint path if available, and record command, inputs, outputs, status, and metrics as evidence.",
            ]
        )
    if not ranked:
        lines.append(
            "- No indexed benchmark comparison history records were returned. You may still inspect the store roots for records/benchmark_result_record.json files if the report topic suggests historical benchmark evidence matters."
        )
    else:
        lines.append("- Candidate benchmark history records:")
        for index, row in enumerate(ranked[:8], start=1):
            metrics = _report_benchmark_history_metrics_preview(row)
            lines.append(
                "  "
                f"{index}. repo={row.get('repo') or 'unknown'}, "
                f"operator_id={row.get('operator_id') or 'unknown'}, "
                f"dataset_key={row.get('dataset_key') or 'unknown'}, "
                f"success={bool(row.get('success'))}, "
                f"returncode={row.get('returncode')}, "
                f"run_id={row.get('run_id') or 'unknown'}, "
                f"metrics={metrics}, "
                f"record_path={row.get('record_path') or ''}"
            )
    if not operator_candidates:
        lines.append(
            "- No matching local operators were returned. If computed evidence is required, report this as a local computation gap instead of inventing predicted values."
        )
    else:
        lines.append("- Candidate local operators for computed_data:")
        for index, candidate in enumerate(operator_candidates[:8], start=1):
            runtime = (
                candidate.get("runtime")
                if isinstance(candidate.get("runtime"), dict)
                else {}
            )
            inputs = (
                candidate.get("inputs")
                if isinstance(candidate.get("inputs"), list)
                else []
            )
            outputs = (
                candidate.get("outputs")
                if isinstance(candidate.get("outputs"), list)
                else []
            )
            input_paths = _preview_io_paths(inputs)
            output_paths = _preview_io_paths(outputs)
            lines.append(
                "  "
                f"{index}. operator_id={candidate.get('operator_id') or 'unknown'}, "
                f"name={candidate.get('name') or 'unknown'}, "
                f"family={candidate.get('family') or 'unknown'}, "
                f"status={candidate.get('validation_status') or 'unknown'}, "
                f"backend={runtime.get('backend') or 'unknown'}, "
                f"image={runtime.get('image_ref') or 'unknown'}, "
                f"workflow={runtime.get('workflow_path') or runtime.get('entry_workflow') or 'unknown'}, "
                f"entrypoint={runtime.get('entrypoint') or 'unknown'}, "
                f"inputs_json={runtime.get('inputs_json_path') or 'unknown'}, "
                f"input_paths={input_paths}, "
                f"output_paths={output_paths}, "
                f"operator_path={candidate.get('operator_path') or ''}"
            )
    if not dataset_store_candidates:
        lines.append(
            "- No matching dataset_store records were returned. Use operator input hints or history records as secondary candidate input bundles."
        )
    else:
        lines.append("- Candidate dataset_store records:")
        for index, candidate in enumerate(dataset_store_candidates[:10], start=1):
            files_preview = _dataset_store_files_preview(candidate)
            lines.append(
                "  "
                f"{index}. dataset_id={candidate.get('dataset_id') or 'unknown'}, "
                f"name={candidate.get('name') or 'unknown'}, "
                f"domain={candidate.get('domain') or 'unknown'}, "
                f"version={candidate.get('version') or 'unknown'}, "
                f"files={files_preview}, "
                f"record_path={candidate.get('record_path') or ''}"
            )
    if dataset_candidates:
        lines.append("- Candidate local datasets/input bundles:")
        for index, item in enumerate(dataset_candidates[:10], start=1):
            lines.append(f"  {index}. {item}")
    lines.append("End report local data source context.")
    if not is_report_local_data:
        lines[-1] = footer
    return "\n".join(lines) + "\n"


def _rank_local_operator_candidates(
    *,
    task: str,
    workspace_root: Path,
    limit: int,
) -> list[dict[str, object]]:
    candidates: dict[str, tuple[int, int, dict[str, object]]] = {}
    query = task.strip()
    for store_root in _candidate_operator_store_roots(workspace_root):
        try:
            store = OperatorStore(store_root)
            rows = store.search_operators(
                OperatorSearchFilter(query=query, limit=max(limit * 2, 12))
            )
        except sqlite3.Error:
            rows = []
        if not rows:
            try:
                store = OperatorStore(store_root)
                rows = store.search_operators(
                    OperatorSearchFilter(limit=max(limit * 2, 12))
                )
            except sqlite3.Error:
                rows = []
        for rank, row in enumerate(rows):
            candidate = _local_operator_candidate_from_search_row(row)
            if candidate is None:
                continue
            operator_id = str(candidate.get("operator_id", "")).strip()
            if not operator_id:
                continue
            searchable = "\n".join(
                [
                    str(candidate.get("name", "")),
                    str(candidate.get("summary", "")),
                    str(candidate.get("canonical_text", "")),
                    " ".join(
                        str(tag)
                        for tag in candidate.get("tags", [])
                        if isinstance(tag, str)
                    ),
                ]
            )
            score = _local_operator_status_score(
                candidate
            ) + 4 * _benchmark_query_overlap_score(
                query=query,
                searchable_text=searchable,
            )
            current = candidates.get(operator_id)
            if (
                current is None
                or score > current[0]
                or (score == current[0] and rank < current[1])
            ):
                candidates[operator_id] = (score, rank, candidate)
    ranked = sorted(
        candidates.values(),
        key=lambda item: (-item[0], item[1], str(item[2].get("name", "")).casefold()),
    )
    return [item[2] for item in ranked[: max(1, limit)]]


def _rank_local_dataset_store_candidates(
    *,
    task: str,
    workspace_root: Path,
    limit: int,
) -> list[dict[str, object]]:
    candidates: dict[str, tuple[int, int, dict[str, object]]] = {}
    query = task.strip()
    for rank, candidate in enumerate(
        _benchmark_user_dataset_candidates(task=task, workspace_root=workspace_root)
    ):
        dataset_id = str(candidate.get("dataset_id", "")).strip()
        if not dataset_id:
            continue
        score = 100_000 + _benchmark_dataset_task_score(
            task=task,
            dataset_candidate=candidate,
        )
        candidates[dataset_id] = (score, rank, candidate)
    for store_root in _candidate_dataset_store_roots(workspace_root):
        try:
            store = DatasetStore(store_root)
            query_rows = store.search_datasets(
                DatasetSearchFilter(query=query, limit=max(limit * 2, 12))
            )
        except sqlite3.Error:
            query_rows = []
        try:
            store = DatasetStore(store_root)
            broad_rows = store.search_datasets(
                DatasetSearchFilter(limit=max(limit * 6, 48))
            )
        except sqlite3.Error:
            broad_rows = []
        rows = query_rows
        seen_dataset_ids = {
            str(row.get("dataset_id", "")).strip()
            for row in query_rows
            if str(row.get("dataset_id", "")).strip()
        }
        rows.extend(
            row
            for row in broad_rows
            if str(row.get("dataset_id", "")).strip() not in seen_dataset_ids
        )
        if not rows:
            try:
                store = DatasetStore(store_root)
                rows = store.search_datasets(
                    DatasetSearchFilter(limit=max(limit * 2, 12))
                )
            except sqlite3.Error:
                rows = []
        for rank, row in enumerate(rows):
            dataset_id = str(row.get("dataset_id", "")).strip()
            if not dataset_id:
                continue
            candidate = _local_dataset_candidate_from_search_row(row)
            searchable = "\n".join(
                [
                    str(candidate.get("name", "")),
                    str(candidate.get("summary", "")),
                    str(candidate.get("domain", "")),
                    str(candidate.get("canonical_text", "")),
                ]
            )
            score = 4 * _benchmark_query_overlap_score(
                query=query, searchable_text=searchable
            )
            score += _benchmark_dataset_task_score(
                task=task, dataset_candidate=candidate
            )
            current = candidates.get(dataset_id)
            if (
                current is None
                or score > current[0]
                or (score == current[0] and rank < current[1])
            ):
                candidates[dataset_id] = (score, rank, candidate)
    ranked = sorted(
        candidates.values(),
        key=lambda item: (-item[0], item[1], str(item[2].get("name", "")).casefold()),
    )
    return [item[2] for item in ranked[: max(1, limit)]]


def _local_dataset_candidate_from_search_row(
    row: dict[str, object],
) -> dict[str, object]:
    record_path_raw = str(row.get("record_path", "")).strip()
    payload: dict[str, object] = {}
    if record_path_raw:
        record_path = Path(record_path_raw)
        if not record_path.is_absolute():
            project_relative = _PROJECT_ROOT / record_path
            if project_relative.exists():
                record_path = project_relative
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    return {
        "dataset_id": str(payload.get("dataset_id", row.get("dataset_id", ""))).strip(),
        "name": str(payload.get("name", row.get("name", ""))).strip(),
        "version": str(payload.get("version", row.get("version", ""))).strip(),
        "domain": str(payload.get("domain", row.get("domain", ""))).strip(),
        "summary": str(payload.get("summary", row.get("summary", ""))).strip(),
        "canonical_text": str(
            payload.get("canonical_text", row.get("canonical_text", ""))
        ).strip(),
        "files": [item for item in payload.get("files", []) if isinstance(item, dict)],
        "tags": [
            str(tag).strip()
            for tag in payload.get("tags", [])
            if isinstance(tag, str) and tag.strip()
        ],
        "compatible_operator_ids": [
            str(item).strip()
            for item in payload.get("compatible_operator_ids", [])
            if isinstance(item, str) and item.strip()
        ],
        "record_path": record_path_raw,
    }


def _local_operator_candidate_from_search_row(
    row: dict[str, object],
) -> dict[str, object] | None:
    operator_path_raw = row.get("operator_path")
    if not isinstance(operator_path_raw, str) or not operator_path_raw.strip():
        return None
    operator_path = Path(operator_path_raw)
    if not operator_path.exists():
        return None
    try:
        payload = json.loads(operator_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    return {
        "operator_id": str(
            payload.get("operator_id", row.get("operator_id", ""))
        ).strip(),
        "name": str(payload.get("name", row.get("name", ""))).strip(),
        "family": str(payload.get("family", row.get("family", ""))).strip(),
        "validation_status": str(
            payload.get(
                "validation_status",
                payload.get("status", row.get("validation_status", "")),
            )
        ).strip(),
        "summary": str(payload.get("summary", "")),
        "canonical_text": str(payload.get("canonical_text", "")),
        "tags": [
            str(tag).strip()
            for tag in payload.get("tags", [])
            if isinstance(tag, str) and tag.strip()
        ],
        "runtime": {
            "backend": str(runtime.get("backend", "")).strip(),
            "image_ref": str(runtime.get("image_ref", "")).strip(),
            "entrypoint": str(runtime.get("entrypoint", "")).strip(),
            "workflow_path": str(runtime.get("workflow_path", "")).strip(),
            "entry_workflow": str(runtime.get("entry_workflow", "")).strip(),
            "inputs_json_path": str(runtime.get("inputs_json_path", "")).strip(),
            "dockerfile_path": str(runtime.get("dockerfile_path", "")).strip(),
        },
        "inputs": [
            item for item in payload.get("inputs", []) if isinstance(item, dict)
        ],
        "outputs": [
            item for item in payload.get("outputs", []) if isinstance(item, dict)
        ],
        "operator_path": str(operator_path),
    }


def _local_operator_status_score(candidate: dict[str, object]) -> int:
    status = str(candidate.get("validation_status", "")).strip()
    if status == "completed":
        return 20
    if status == "registered_ready":
        return 16
    if status == "registered":
        return 10
    if status == "partial":
        return 5
    return 1


def _preview_io_paths(items: list[object], *, max_items: int = 4) -> str:
    paths: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path", "")).strip()
        name = str(item.get("name", "")).strip()
        if raw_path:
            paths.append(raw_path)
        elif name:
            paths.append(name)
    if not paths:
        return "none"
    compact = paths[:max_items]
    if len(paths) > max_items:
        compact.append(f"... {len(paths) - max_items} more")
    return "; ".join(compact)


def _dataset_store_files_preview(
    candidate: dict[str, object], *, max_items: int = 4
) -> str:
    files = candidate.get("files") if isinstance(candidate.get("files"), list) else []
    previews: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri", "")).strip()
        name = str(item.get("name", "")).strip()
        media_type = str(item.get("media_type", "")).strip()
        label = uri or name
        if not label:
            continue
        if media_type:
            label = f"{label} ({media_type})"
        previews.append(label)
    if not previews:
        return "none"
    compact = previews[:max_items]
    if len(previews) > max_items:
        compact.append(f"... {len(previews) - max_items} more")
    return "; ".join(compact)


def _local_dataset_candidates(
    *,
    history_rows: list[dict[str, object]],
    operator_candidates: list[dict[str, object]],
    dataset_store_candidates: list[dict[str, object]],
) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    def add(label: str) -> None:
        label = label.strip()
        if not label or label in seen:
            return
        seen.add(label)
        candidates.append(label)

    for row in history_rows:
        dataset_key = str(row.get("dataset_key", "")).strip() or "unknown"
        result_files = row.get("result_files")
        result_preview = ""
        if isinstance(result_files, list) and result_files:
            result_preview = (
                f", result_files={'; '.join(str(item) for item in result_files[:3])}"
            )
        add(
            f"history dataset_key={dataset_key}, operator_id={row.get('operator_id') or 'unknown'}, run_id={row.get('run_id') or 'unknown'}{result_preview}"
        )
    for candidate in operator_candidates:
        name = str(candidate.get("name", "")).strip() or "unknown"
        inputs = (
            candidate.get("inputs") if isinstance(candidate.get("inputs"), list) else []
        )
        input_paths = _preview_io_paths(inputs)
        runtime = (
            candidate.get("runtime")
            if isinstance(candidate.get("runtime"), dict)
            else {}
        )
        inputs_json = str(runtime.get("inputs_json_path", "")).strip()
        if inputs_json and inputs_json != "unknown":
            add(f"operator {name} inputs_json={inputs_json}, input_paths={input_paths}")
        elif input_paths != "none":
            add(f"operator {name} input_paths={input_paths}")
    for candidate in dataset_store_candidates:
        dataset_id = str(candidate.get("dataset_id", "")).strip() or "unknown"
        files_preview = _dataset_store_files_preview(candidate)
        add(
            f"dataset_store dataset_id={dataset_id}, name={candidate.get('name') or 'unknown'}, files={files_preview}, record_path={candidate.get('record_path') or ''}"
        )
    return candidates


def _rank_report_benchmark_history_rows(
    *,
    task: str,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not rows:
        return []
    query = task.strip()
    indexed_rows = list(enumerate(rows))

    def score(item: tuple[int, dict[str, object]]) -> tuple[int, int]:
        index, row = item
        text = " ".join(
            str(row.get(key, ""))
            for key in (
                "repo",
                "operator_id",
                "dataset_key",
                "workflow_signature",
                "input_signature",
                "canonical_text",
            )
        )
        overlap = (
            _benchmark_query_overlap_score(query=query, searchable_text=text)
            if query
            else 0
        )
        success_bonus = 2 if bool(row.get("success")) else 0
        return (-(overlap + success_bonus), index)

    return [row for _, row in sorted(indexed_rows, key=score)]


def _report_benchmark_history_metrics_preview(row: dict[str, object]) -> str:
    record_path = str(row.get("record_path", "")).strip()
    if not record_path:
        return "{}"
    try:
        payload = json.loads(Path(record_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "{}"
    analysis = payload.get("analysis_payload")
    metrics: object = {}
    if isinstance(analysis, dict):
        metrics = analysis.get("metrics", {})
    if not isinstance(metrics, dict) or not metrics:
        return "{}"
    compact = {str(key): value for key, value in list(metrics.items())[:6]}
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def _compact_path_list(paths: list[str], *, max_items: int = 8) -> list[str]:
    if len(paths) <= max_items:
        return paths
    remaining = len(paths) - max_items
    return [*paths[:max_items], f"... {remaining} more paths omitted"]


def _summarize_worker_output_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    node = payload.get("node") if isinstance(payload.get("node"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    summary = {
        "node_id": node.get("node_id"),
        "title": node.get("title"),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "next_action_hint": result.get("next_action_hint"),
        "failure_reason": result.get("failure_reason"),
        "artifacts_count": len(result.get("artifacts", []) or []),
        "evidence_count": len(result.get("evidence", []) or []),
    }
    if isinstance(result.get("spawned_subgraph"), dict):
        spawned = result.get("spawned_subgraph")
        nodes = spawned.get("nodes") if isinstance(spawned.get("nodes"), list) else []
        edges = spawned.get("edges") if isinstance(spawned.get("edges"), list) else []
        summary["spawned_subgraph_summary"] = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_ids": [
                str(item.get("node_id"))
                for item in nodes[:8]
                if isinstance(item, dict) and item.get("node_id")
            ],
        }
    return summary


def _compact_metadata_hint(metadata: dict[str, Any]) -> str:
    hint_payload = {
        "task_type": metadata.get("task_type"),
        "graph_round": metadata.get("graph_round"),
        "guidance_ids": metadata.get("guidance_ids", []),
        "worker_role": metadata.get("worker_role"),
    }
    if metadata.get("retrieved_cases"):
        retrieved_cases = metadata.get("retrieved_cases")
        if isinstance(retrieved_cases, list):
            hint_payload["retrieved_case_count"] = len(retrieved_cases)
            hint_payload["retrieved_case_types"] = [
                str(item.get("task_type"))
                for item in retrieved_cases[:4]
                if isinstance(item, dict)
            ]
    return f"\nNode metadata summary: {json.dumps(hint_payload, ensure_ascii=False, sort_keys=True)}"


def _final_response_source_material(node: TaskNode) -> str:
    if node.node_id != "final_response":
        return ""
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    payload = {
        "decision": metadata.get("final_decision"),
        "reason": metadata.get("final_decision_reason"),
        "failed_nodes": metadata.get("failed_nodes", []),
        "task_type": metadata.get("task_type"),
    }
    benchmark_dataset_material = ""
    if str(metadata.get("task_type", "")) == "benchmark":
        run_dir_raw = metadata.get("run_dir")
        if isinstance(run_dir_raw, str) and run_dir_raw.strip():
            benchmark_dataset_material = _benchmark_final_response_dataset_material(
                Path(run_dir_raw.strip())
            )
    run_dir_raw = metadata.get("run_dir")
    run_dir = (
        Path(run_dir_raw)
        if isinstance(run_dir_raw, str) and run_dir_raw.strip()
        else None
    )
    final_summary = str(metadata.get("final_summary", ""))
    if run_dir is not None:
        final_summary = _relativize_user_facing_paths(final_summary, run_dir=run_dir)
    fallback_candidate = str(metadata.get("fallback_candidate", "")).strip()
    if run_dir is not None and fallback_candidate:
        fallback_candidate = _relativize_user_facing_paths(
            fallback_candidate,
            run_dir=run_dir,
        )
    fallback_block = (
        f"- Deterministic natural-language fallback draft:\n{fallback_candidate}\n"
        if fallback_candidate
        else ""
    )
    return (
        "Final response source material:\n"
        f"- Original user task: {metadata.get('task', '')}\n"
        f"- Supervisor decision: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
        f"{fallback_block}"
        f"- Supervisor final summary:\n{final_summary}\n"
        f"{benchmark_dataset_material}"
        "End final response source material.\n"
    )


def _benchmark_final_response_dataset_material(run_dir: Path) -> str:
    dataset_resolution_path = run_dir / "dataset_resolution.json"
    metric_plan_path = run_dir / "metric_plan.json"
    register_report_path = run_dir / "register_report.json"

    dataset_resolution: dict[str, Any] = {}
    metric_plan: dict[str, Any] = {}
    register_report: dict[str, Any] = {}

    for path, target in (
        (dataset_resolution_path, dataset_resolution),
        (metric_plan_path, metric_plan),
        (register_report_path, register_report),
    ):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            target.update(payload)

    selection_dataset_key = str(
        register_report.get("selection_dataset_key", "")
    ).strip()
    shared_datasets = [
        str(item).strip()
        for item in register_report.get("shared_datasets", []) or []
        if str(item).strip()
    ]
    repo_to_dataset = {}
    raw_repo_to_dataset = dataset_resolution.get("repo_to_dataset")
    if isinstance(raw_repo_to_dataset, dict):
        repo_to_dataset = {
            str(repo): str(dataset_key)
            for repo, dataset_key in raw_repo_to_dataset.items()
        }

    metric_rows = metric_plan.get("rows")
    dataset_lines: list[str] = []
    if selection_dataset_key:
        dataset_lines.append(f"- selection_dataset_key: `{selection_dataset_key}`")
    if shared_datasets:
        dataset_lines.append(f"- shared_datasets: `{', '.join(shared_datasets)}`")
    if repo_to_dataset:
        repo_pairs = ", ".join(
            f"{repo} -> {dataset_key or 'unknown'}"
            for repo, dataset_key in sorted(repo_to_dataset.items())
        )
        dataset_lines.append(f"- repo_to_dataset: {repo_pairs}")
    if isinstance(metric_rows, list) and metric_rows:
        for row in metric_rows[:8]:
            if not isinstance(row, dict):
                continue
            repo = str(row.get("repo", "")).strip() or "unknown"
            dataset_key = str(row.get("dataset_key", "")).strip() or "unknown"
            selected_inputs = row.get("selected_input_files")
            input_names: list[str] = []
            if isinstance(selected_inputs, dict):
                input_names = [str(name) for name in selected_inputs.keys()][:6]
            inputs_display = ", ".join(input_names) if input_names else "none"
            dataset_lines.append(
                f"- {repo}: dataset `{dataset_key}`, selected_inputs `{inputs_display}`"
            )
    if not dataset_lines:
        dataset_lines.append(
            "- No dataset manifest was resolved; if you mention a dataset in the final response, derive it conservatively from the benchmark root and actual staged inputs only."
        )

    return "Benchmark dataset context:\n" + "\n".join(dataset_lines) + "\n"


def _parse_worker_result(text: str) -> WorkerResult:
    payload = _extract_json_object(text)
    if payload is None:
        return WorkerResult(
            status="completed",
            summary=text.strip() or "Worker completed.",
            spawned_subgraph=_extract_spawned_subgraph_from_text(text),
        )
    status = str(payload.get("status", "completed"))
    if status not in {"completed", "blocked", "failed", "partial"}:
        status = "partial"
    return WorkerResult(
        status=status,  # type: ignore[arg-type]
        summary=str(payload.get("summary", text.strip() or "Worker completed.")),
        artifacts=[str(item) for item in payload.get("artifacts", []) or []],
        evidence=[str(item) for item in payload.get("evidence", []) or []],
        next_action_hint=_optional_str(payload.get("next_action_hint")),
        failure_reason=_optional_str(payload.get("failure_reason")),
        spawned_subgraph=payload.get("spawned_subgraph")
        if isinstance(payload.get("spawned_subgraph"), dict)
        else None,
    )


def _postprocess_worker_result(
    *,
    node: TaskNode,
    result: WorkerResult,
    run_dir: Path,
) -> WorkerResult:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    if str(metadata.get("task_type", "")).strip() != "report":
        return result
    if node.node_id == "compose_report":
        return _postprocess_compose_report_result(result=result, run_dir=run_dir)
    return result


def _postprocess_compose_report_result(
    *,
    result: WorkerResult,
    run_dir: Path,
) -> WorkerResult:
    """Ensure compose_report leaves a concrete report artifact for final delivery."""

    report_path = _materialize_report_artifact_from_existing_paths(
        run_dir=run_dir,
        artifacts=result.artifacts,
    )
    if report_path is not None:
        return _with_report_artifact(result=result, report_path=report_path)

    summary = _clean_user_response_text(result.summary)
    if _looks_like_markdown_report(summary):
        report_path = run_dir / "composed_report" / "final_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            _normalize_report_markdown_syntax(summary).strip(),
            encoding="utf-8",
        )
        return _with_report_artifact(
            result=WorkerResult(
                status=result.status,
                summary=f"Final report written to {report_path}.",
                artifacts=list(result.artifacts),
                evidence=list(result.evidence),
                next_action_hint=result.next_action_hint,
                failure_reason=result.failure_reason,
                spawned_subgraph=result.spawned_subgraph,
            ),
            report_path=report_path,
        )

    if result.status == "completed":
        return WorkerResult(
            status="partial",
            summary=(
                "compose_report completed without a user-facing final report artifact; "
                "the report needs to be composed or retried from the available lane evidence."
            ),
            artifacts=list(result.artifacts),
            evidence=list(result.evidence),
            next_action_hint=(
                "Create composed_report/final_report.md from the completed report lanes, "
                "using valid Markdown heading/list spacing and paragraph-led prose."
            ),
            failure_reason="missing_final_report_artifact",
            spawned_subgraph=result.spawned_subgraph,
        )
    return result


def _with_report_artifact(*, result: WorkerResult, report_path: Path) -> WorkerResult:
    artifact = str(report_path)
    artifacts = list(dict.fromkeys([*result.artifacts, artifact]))
    summary = result.summary
    if not summary.strip() or _is_placeholder_worker_summary(summary):
        summary = f"Final report written to {report_path}."
    return WorkerResult(
        status=result.status,
        summary=summary,
        artifacts=artifacts,
        evidence=list(result.evidence),
        next_action_hint=result.next_action_hint,
        failure_reason=result.failure_reason,
        spawned_subgraph=result.spawned_subgraph,
    )


def _materialize_report_artifact_from_existing_paths(
    *,
    run_dir: Path,
    artifacts: list[str],
) -> Path | None:
    canonical = run_dir / "composed_report" / "final_report.md"
    candidates: list[Path] = [canonical, run_dir / "compose" / "final_report.md"]
    for artifact in artifacts:
        artifact_path = Path(artifact)
        if not artifact_path.is_absolute():
            artifact_path = run_dir / artifact_path
        if artifact_path.name == "final_report.md":
            candidates.append(artifact_path)

    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if (
            not text
            or _is_placeholder_worker_summary(text)
            or _is_internal_supervisor_diagnostic(text)
        ):
            continue
        normalized = _normalize_report_markdown_syntax(text).strip()
        if candidate == canonical:
            if normalized != text:
                candidate.write_text(normalized, encoding="utf-8")
            return canonical
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(normalized, encoding="utf-8")
        return canonical
    return None


def _looks_like_markdown_report(text: str) -> bool:
    if len(text.strip()) < 300:
        return False
    return bool(re.search(r"(?m)^#\s*\S+", text)) and bool(
        re.search(r"(?m)^##\s*\S+", text)
    )


def _normalize_report_markdown_syntax(text: str) -> str:
    """Repair common spacing mistakes that make generated reports invalid Markdown."""

    lines: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            lines.append(line)
            continue
        if in_fence:
            lines.append(line)
            continue

        fixed = re.sub(r"^(#{1,6})([^#\s].*)$", r"\1 \2", line)
        fixed = re.sub(
            r"^(#{1,6}\s+)((?:\d\s*){4})\s*-\s*((?:\d\s*){4})(?=\D|$)",
            lambda match: (
                f"{match.group(1)}{''.join(match.group(2).split())}"
                f"-{''.join(match.group(3).split())}"
            ),
            fixed,
        )
        fixed = re.sub(r"^(#{1,6}\s+)(\d+(?:\.\d+)*)\s+\.\s+", r"\1\2. ", fixed)
        fixed = re.sub(r"^(#{1,6}\s+)(\d+(?:\.\d+)*\.?)(?=[^\s\d.-])", r"\1\2 ", fixed)
        fixed = re.sub(r"^(\s*)(\d+\.)(?=\S)", r"\1\2 ", fixed)
        fixed = re.sub(r"^(\s*)([-*+])(?=[^\s\-*+])", r"\1\2 ", fixed)
        lines.append(fixed)
    return "\n".join(lines)


def _extract_spawned_subgraph_from_text(text: str) -> dict[str, Any] | None:
    """Recover spawned_subgraph when the surrounding worker JSON is slightly malformed."""

    match = re.search(r'"spawned_subgraph"\s*:\s*\{', text)
    if match is None:
        return None
    start = match.end() - 1
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : index + 1]
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    return None
                return payload if isinstance(payload, dict) else None
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidate = fenced.group(1) if fenced else stripped
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        payload = _extract_payload_from_python_repr(candidate)
        if payload is None:
            return None
    return _extract_payload_from_object(payload)


def _extract_generic_json_payload(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidate = fenced.group(1) if fenced else stripped
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            payload = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            return None
    return payload if isinstance(payload, dict) else None


def _extract_payload_from_python_repr(text: str) -> dict[str, Any] | None:
    """Best-effort parse for Python repr payloads from model responses."""

    try:
        payload = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None
    return _extract_payload_from_object(payload)


def _extract_payload_from_object(payload: object) -> dict[str, Any] | None:
    """Extract the first worker-result JSON object from nested payload shapes."""

    if isinstance(payload, dict):
        if _looks_like_worker_result_dict(payload):
            return payload
        text_value = payload.get("text")
        if isinstance(text_value, str):
            nested = _extract_json_object(text_value)
            if nested is not None:
                return nested
        content_value = payload.get("content")
        if isinstance(content_value, str):
            nested = _extract_json_object(content_value)
            if nested is not None:
                return nested
        return None
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_payload_from_object(item)
            if nested is not None:
                return nested
    return None


def _looks_like_worker_result_dict(payload: dict[str, Any]) -> bool:
    """Return whether the dict resembles the expected worker result schema."""

    return "status" in payload and (
        "summary" in payload
        or "artifacts" in payload
        or "evidence" in payload
        or "failure_reason" in payload
    )


def _looks_like_user_delivery_node(node_id: str) -> bool:
    normalized = node_id.lower()
    if normalized in {
        "compose_generic",
        "compose_report",
        "final_summarize",
        "final_summary",
        "final_answer",
        "final_response",
    }:
        return True
    return any(
        marker in normalized for marker in ("answer", "reply", "response", "deliver")
    )


def _last_ai_text(messages: list[Any]) -> str:
    last_text = ""
    current_text = ""
    for message in messages:
        message_type = str(getattr(message, "type", "") or "")
        class_name = type(message).__name__
        if message_type == "tool" or isinstance(message, ToolMessage):
            current_text = ""
            continue
        if message_type != "ai" and "AIMessage" not in class_name:
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            if content.strip():
                current_text += content
                last_text = current_text
            continue
        rendered = str(content).strip()
        if rendered:
            current_text += rendered
            last_text = current_text
    return last_text


def _message_text(response: object) -> str:
    if isinstance(response, AIMessage):
        content = response.content
        if isinstance(content, str):
            return content
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    return str(response)


def _extract_task_classifier_payload(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidate = fenced.group(1) if fenced else stripped
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


async def _render_user_response(
    *,
    task: str,
    task_type: str,
    rounds,
    decision: SupervisorDecision,
    final_summary: str,
    run_dir: Path,
    worker_runner,
) -> str:
    """Use a final LLM pass for the chat-facing answer.

    The full supervisor diagnostics remain in final_summary.md. The finalizer is
    intentionally narrow: it may rewrite and select from existing worker results,
    but it must not add new facts or turn partial work into a claimed success.
    """

    fallback_candidate = _select_user_response_candidate(
        task_type=task_type,
        rounds=rounds,
    )
    fallback = _build_fallback_user_response(
        task=task,
        task_type=task_type,
        rounds=rounds,
        decision=decision,
        preferred_candidate=fallback_candidate,
    )
    if task_type == "report":
        composed_report = _report_composed_final_report_candidate(run_dir)
        if composed_report:
            return _relativize_user_facing_paths(
                _normalize_report_markdown_syntax(composed_report),
                run_dir=run_dir,
            )
    finalizer_node = TaskNode(
        node_id="final_response",
        title="Write final user response",
        objective=(
            "Turn the supervisor run result into the final answer shown to the user. "
            "Prefer successful findings and useful next information; keep failures brief "
            "unless they change the answer's reliability."
        ),
        capability_bundles=["summarize", "validate"],
        metadata={
            "task": task,
            "task_type": task_type,
            "final_summary": final_summary,
            "final_decision": decision.decision,
            "final_decision_reason": decision.reason,
            "failed_nodes": list(decision.failed_nodes),
            "fallback_candidate": fallback,
        },
    )
    try:
        result = await _run_worker_and_capture(
            node=finalizer_node,
            graph_round=len(rounds) + 1,
            run_dir=run_dir,
            worker_runner=worker_runner,
        )
    except GraphBubbleUp:
        raise
    except Exception:
        return _relativize_user_facing_paths(fallback, run_dir=run_dir)
    finalizer_summary = _clean_user_response_text(result.summary)
    if (
        result.status in {"completed", "partial"}
        and finalizer_summary
        and not _is_placeholder_worker_summary(finalizer_summary)
        and not _is_internal_supervisor_diagnostic(finalizer_summary)
    ):
        if task_type == "report":
            finalizer_summary = _normalize_report_markdown_syntax(finalizer_summary)
        return _relativize_user_facing_paths(
            finalizer_summary,
            run_dir=run_dir,
        )
    if task_type == "report":
        fallback = _normalize_report_markdown_syntax(fallback)
    return _relativize_user_facing_paths(fallback, run_dir=run_dir)


def _report_composed_final_report_candidate(run_dir: Path) -> str | None:
    """Return the composed report artifact when it is already user-facing."""

    report_path = _materialize_report_artifact_from_existing_paths(
        run_dir=run_dir,
        artifacts=[],
    )
    if report_path is None:
        return None
    try:
        text = report_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    if _is_placeholder_worker_summary(text) or _is_internal_supervisor_diagnostic(text):
        return None
    return text


def _is_placeholder_worker_summary(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip()).casefold()
    return normalized in {
        "worker completed.",
        "worker completed",
    }


def _is_internal_supervisor_diagnostic(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip()).casefold()
    if not normalized:
        return False
    if "supervisor summary" in normalized and (
        "round" in normalized or "decision:" in normalized or "- task:" in normalized
    ):
        return True
    return normalized.startswith("# supervisor summary") or normalized.startswith(
        "supervisor summary"
    )


def _select_user_response_candidate(*, task_type: str, rounds) -> str | None:
    candidates: list[tuple[int, str]] = []
    for round_offset, round_result in enumerate(reversed(rounds)):
        round_penalty = round_offset * 10
        for item_offset, item in enumerate(reversed(round_result.node_results)):
            if item.status != "completed":
                continue
            cleaned = _clean_user_response_text(str(item.summary or ""))
            if not cleaned:
                continue
            if _is_placeholder_worker_summary(cleaned):
                continue
            if _is_internal_supervisor_diagnostic(cleaned):
                continue
            score = (
                _user_response_node_score(str(item.node_id), task_type=task_type)
                - round_penalty
                - item_offset
            )
            score += _user_response_text_score(cleaned)
            candidates.append((score, cleaned))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_text = candidates[0]
    if best_score < 0:
        return None
    return best_text


def _build_fallback_user_response(
    *,
    task: str,
    task_type: str,
    rounds,
    decision: SupervisorDecision,
    preferred_candidate: str | None,
) -> str:
    """Render deterministic chat-facing text when the final LLM pass is unusable."""

    candidate = (preferred_candidate or "").strip()
    if (
        candidate
        and not _is_placeholder_worker_summary(candidate)
        and not _is_internal_supervisor_diagnostic(candidate)
    ):
        if _task_prefers_chinese_response(task) and not re.search(
            r"[\u3400-\u9fff]",
            candidate,
        ):
            return f"这次已有可用结果：{_truncate_user_facing_summary(candidate)}"
        return candidate
    if _task_prefers_chinese_response(task):
        return _build_fallback_user_response_zh(
            task_type=task_type,
            rounds=rounds,
            decision=decision,
        )
    return _build_fallback_user_response_en(
        task_type=task_type,
        rounds=rounds,
        decision=decision,
    )


def _build_fallback_user_response_zh(
    *,
    task_type: str,
    rounds,
    decision: SupervisorDecision,
) -> str:
    items = _fallback_user_visible_items(rounds)
    summaries = " ".join(str(item.summary or "") for item in items)
    if _summary_indicates_missing_repository(summaries):
        return (
            "这次还没法真正开始部署：没有拿到要部署的仓库 URL 或本地源码路径，"
            "当前工作区里也没有可检查的源码。为了避免基于空工作区继续构建、测试或生成不可靠结论，"
            "我已经提前停止，后续构建和工作流验证没有继续执行。\n\n"
            "请补充 GitHub 仓库地址或本地仓库路径后再试，我就可以继续做仓库检查、构建和验证。"
        )

    unresolved = _rounds_have_unresolved_nodes(rounds) or bool(decision.failed_nodes)
    opening = "这次没有完整完成。" if unresolved else "这次已经完成。"
    reason = _humanize_decision_reason_zh(decision.reason)
    paragraphs = [f"{opening}{reason}"]

    detail_sentences = [
        sentence for item in items[:3] if (sentence := _fallback_item_sentence_zh(item))
    ]
    if detail_sentences:
        paragraphs.append("目前可确认的是：" + "；".join(detail_sentences) + "。")

    if unresolved:
        paragraphs.append(_next_step_hint_zh(task_type))
    return "\n\n".join(paragraphs)


def _build_fallback_user_response_en(
    *,
    task_type: str,
    rounds,
    decision: SupervisorDecision,
) -> str:
    items = _fallback_user_visible_items(rounds)
    summaries = " ".join(str(item.summary or "") for item in items)
    if _summary_indicates_missing_repository(summaries):
        return (
            "I could not start the repository deployment because no repository URL, "
            "local source path, or materialized source tree was available in the workspace. "
            "I stopped before build or workflow validation so the final answer would not "
            "claim unsupported progress.\n\n"
            "Please provide a GitHub repository URL or a local repository path, then I can "
            "continue with inspection, build, and validation."
        )

    unresolved = _rounds_have_unresolved_nodes(rounds) or bool(decision.failed_nodes)
    opening = "This run did not complete." if unresolved else "This run completed."
    reason = _humanize_decision_reason_en(decision.reason)
    paragraphs = [f"{opening}{reason}"]
    detail_sentences = [
        sentence for item in items[:3] if (sentence := _fallback_item_sentence_en(item))
    ]
    if detail_sentences:
        paragraphs.append("What I can confirm: " + "; ".join(detail_sentences) + ".")
    if unresolved:
        paragraphs.append(_next_step_hint_en(task_type))
    return "\n\n".join(paragraphs)


def _fallback_user_visible_items(rounds) -> list[Any]:
    primary: list[Any] = []
    secondary: list[Any] = []
    for round_result in rounds:
        for item in round_result.node_results:
            cleaned = _clean_user_response_text(str(item.summary or ""))
            if not cleaned:
                continue
            if _is_placeholder_worker_summary(
                cleaned
            ) or _is_internal_supervisor_diagnostic(cleaned):
                continue
            node_id = str(item.node_id)
            failure_reason = str(item.failure_reason or "")
            if node_id.startswith("check_"):
                continue
            if failure_reason in {
                "blocked_by_node_decision_check",
                "blocked_by_failed_dependency",
                "blocked_by_unresolved_dependency",
            }:
                secondary.append(item)
                continue
            if item.status in {"failed", "blocked", "partial"}:
                primary.append(item)
            elif item.status == "completed":
                secondary.append(item)
    return primary or secondary


def _rounds_have_unresolved_nodes(rounds) -> bool:
    for round_result in rounds:
        for item in round_result.node_results:
            if item.status in {"failed", "blocked", "partial"}:
                return True
    return False


def _task_prefers_chinese_response(task: str) -> bool:
    lowered = task.casefold()
    english_markers = (
        "reply in english",
        "respond in english",
        "answer in english",
        "english only",
        "in english",
        "用英文",
        "使用英文",
        "英文回答",
        "英语回答",
    )
    if any(marker in lowered for marker in english_markers):
        return False
    chinese_markers = ("中文", "汉语", "用中文", "中文回答")
    if any(marker in lowered for marker in chinese_markers):
        return True
    return True


def _summary_indicates_missing_repository(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "does not include a repository url or source path",
            "no materialized software repository",
            "nothing to inspect for build/test assets",
            "missing repository url",
            "missing_repo",
            "missing source path",
        )
    )


def _humanize_decision_reason_zh(reason: str) -> str:
    normalized = reason.strip().casefold()
    if not normalized:
        return ""
    if normalized == "node decision check requested finalization.":
        return "前置检查认为继续执行不可靠，所以已提前结束。"
    if normalized == "reached max rounds with unresolved nodes.":
        return "达到本次执行轮次上限后仍有未解决问题。"
    if normalized == "all nodes completed.":
        return "所有步骤都已正常完成。"
    if normalized == "no rounds executed.":
        return "流程还没有实际开始。"
    if normalized == "replan to retry unresolved nodes.":
        return "仍需要重试未解决的步骤。"
    return f"原因是：{reason}"


def _humanize_decision_reason_en(reason: str) -> str:
    normalized = reason.strip().casefold()
    if not normalized:
        return ""
    if normalized == "node decision check requested finalization.":
        return " A prerequisite check determined that continuing would be unreliable."
    if normalized == "reached max rounds with unresolved nodes.":
        return " The run reached the maximum number of rounds with unresolved work."
    if normalized == "all nodes completed.":
        return " All steps completed normally."
    if normalized == "no rounds executed.":
        return " No execution round actually started."
    if normalized == "replan to retry unresolved nodes.":
        return " Some unresolved steps still need a retry."
    return f" Reason: {reason}"


def _fallback_item_sentence_zh(item: Any) -> str:
    summary = _humanize_worker_summary_zh(str(item.summary or ""))
    label = _node_label_zh(str(item.node_id))
    status = _status_label_zh(str(item.status))
    if summary:
        return f"{label}{status}：{summary}"
    return f"{label}{status}"


def _fallback_item_sentence_en(item: Any) -> str:
    summary = _humanize_worker_summary_en(str(item.summary or ""))
    label = _node_label_en(str(item.node_id))
    status = _status_label_en(str(item.status))
    if summary:
        return f"{label} {status}: {summary}"
    return f"{label} {status}"


def _humanize_worker_summary_zh(summary: str) -> str:
    text = _clean_user_response_text(summary)
    lowered = text.casefold()
    if _summary_indicates_missing_repository(text):
        return "没有拿到仓库 URL 或本地源码路径，当前工作区也没有可检查的源码"
    if "blocked by failed dependency" in lowered:
        return "依赖的前置步骤没有通过，所以已跳过"
    if "blocked by unresolved dependency chain" in lowered:
        return "依赖链没有形成可执行结果，所以已跳过"
    if "skipped because node decision check requested finalization" in lowered:
        return "前置检查已经要求提前结束，所以已跳过"
    if "timed out" in lowered:
        return "执行超时，当前结果不完整"
    if "unexpected exception" in lowered:
        return "执行过程中遇到未预期异常"
    return _truncate_user_facing_summary(text)


def _humanize_worker_summary_en(summary: str) -> str:
    text = _clean_user_response_text(summary)
    lowered = text.casefold()
    if _summary_indicates_missing_repository(text):
        return "no repository URL, local source path, or source tree was available"
    if "blocked by failed dependency" in lowered:
        return "a prerequisite step failed, so this step was skipped"
    if "blocked by unresolved dependency chain" in lowered:
        return "the dependency chain did not produce an executable result"
    if "skipped because node decision check requested finalization" in lowered:
        return "a prerequisite check requested early finalization"
    if "timed out" in lowered:
        return "execution timed out, so the result is incomplete"
    if "unexpected exception" in lowered:
        return "an unexpected exception occurred"
    return _truncate_user_facing_summary(text)


def _truncate_user_facing_summary(text: str, *, max_chars: int = 260) -> str:
    stripped = re.sub(r"\s+", " ", text.strip())
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3].rstrip() + "..."


def _node_label_zh(node_id: str) -> str:
    normalized = node_id.lower().removeprefix("retry_")
    labels = {
        "inspect": "仓库检查",
        "build": "构建验证",
        "wdl": "工作流验证",
        "summarize": "结果汇总",
        "register": "任务准备",
        "init_generic": "任务规划",
        "compose_generic": "答案整理",
        "init_report": "报告规划",
        "compose_report": "报告撰写",
        "final_response": "最终回答",
    }
    return labels.get(normalized, "当前步骤")


def _node_label_en(node_id: str) -> str:
    normalized = node_id.lower().removeprefix("retry_")
    labels = {
        "inspect": "repository inspection",
        "build": "build validation",
        "wdl": "workflow validation",
        "summarize": "result summary",
        "register": "task preparation",
        "init_generic": "task planning",
        "compose_generic": "answer composition",
        "init_report": "report planning",
        "compose_report": "report writing",
        "final_response": "final response",
    }
    return labels.get(normalized, "the current step")


def _status_label_zh(status: str) -> str:
    return {
        "completed": "已完成",
        "partial": "只完成了一部分",
        "failed": "失败",
        "blocked": "没有继续",
    }.get(status, "状态不明确")


def _status_label_en(status: str) -> str:
    return {
        "completed": "completed",
        "partial": "partially completed",
        "failed": "failed",
        "blocked": "was blocked",
    }.get(status, "has an unclear status")


def _next_step_hint_zh(task_type: str) -> str:
    if task_type == "github2workspace":
        return (
            "下一步需要补充可访问的仓库地址或本地源码路径，然后再继续检查、构建和验证。"
        )
    if task_type == "benchmark":
        return "下一步需要补充可运行的 benchmark 输入、工具或数据集约束后再继续。"
    if task_type == "report":
        return "下一步需要补充缺失证据或放宽不可用来源后再继续生成完整报告。"
    return "下一步需要补充缺失信息或处理上面的阻塞点后再继续。"


def _next_step_hint_en(task_type: str) -> str:
    if task_type == "github2workspace":
        return (
            "Next, provide an accessible repository URL or local source path, then rerun "
            "inspection, build, and validation."
        )
    if task_type == "benchmark":
        return "Next, provide runnable benchmark inputs, tool constraints, or dataset details, then retry."
    if task_type == "report":
        return "Next, provide the missing evidence or allow alternate sources before composing the full report."
    return "Next, provide the missing information or resolve the blocker above, then retry."


def _user_response_node_score(node_id: str, *, task_type: str) -> int:
    normalized = node_id.lower()
    score = 0
    if normalized.startswith(("init_", "retry_")):
        score -= 60
    if normalized == "summarize":
        score -= 15
    if task_type == "generic":
        score += 10
    if normalized in {"final_answer", "final_response", "final_summarize"}:
        score += 80
    elif normalized in {"compose_generic", "compose_report"}:
        score += 60
    elif _looks_like_user_delivery_node(normalized):
        score += 45
    return score


def _user_response_text_score(text: str) -> int:
    lowered = text.casefold()
    score = 0
    diagnostic_markers = (
        "worker 贡献",
        "blockers",
        "下一步建议",
        "最强已验证结果",
        "supervisor summary",
        "round ",
        "node ",
    )
    if any(marker in lowered for marker in diagnostic_markers):
        score -= 35
    if len(text) <= 500:
        score += 10
    if "\n\n" not in text and text.count("\n") <= 2:
        score += 10
    return score


def _clean_user_response_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    quoted = _extract_quoted_final_answer(stripped)
    if quoted is not None:
        return quoted
    return stripped


def _relativize_user_facing_paths(text: str, *, run_dir: Path) -> str:
    """Hide machine-local absolute paths in user-facing final responses."""

    if not text:
        return text

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        path_text, trailing = _split_trailing_path_punctuation(token)
        replacement = _user_facing_relative_path(path_text, run_dir=run_dir)
        return f"{replacement}{trailing}"

    relativized = _LOCAL_ABSOLUTE_PATH_RE.sub(replace, text)
    return _strip_current_run_relative_prefixes(relativized, run_dir=run_dir)


def _strip_current_run_relative_prefixes(text: str, *, run_dir: Path) -> str:
    """Prefer run-relative paths for artifacts under the current run directory."""

    prefixes = [f"orchestration_runs/{run_dir.name}/"]
    try:
        project_relative_run = run_dir.resolve(strict=False).relative_to(
            _PROJECT_ROOT.resolve(strict=False)
        )
    except ValueError:
        project_relative_run = None
    if project_relative_run is not None:
        prefixes.append(f"{project_relative_run.as_posix()}/")
    for prefix in sorted(set(prefixes), key=len, reverse=True):
        text = text.replace(prefix, "")
    return text


def _split_trailing_path_punctuation(path_text: str) -> tuple[str, str]:
    trailing = ""
    while path_text and path_text[-1] in ".,;:!?，。；：！？、)]}":
        trailing = path_text[-1] + trailing
        path_text = path_text[:-1]
    return path_text, trailing


def _user_facing_relative_path(path_text: str, *, run_dir: Path) -> str:
    path = Path(path_text)
    if not path.is_absolute():
        return path_text
    resolved = path.resolve(strict=False)
    run_root = run_dir.resolve(strict=False)
    project_root = _PROJECT_ROOT.resolve(strict=False)
    if resolved != run_root and _is_relative_to(resolved, run_root):
        return resolved.relative_to(run_root).as_posix()
    if _is_relative_to(resolved, project_root):
        return resolved.relative_to(project_root).as_posix()
    return path_text


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _extract_quoted_final_answer(text: str) -> str | None:
    if len(text) > 800:
        return None
    if not any(
        marker in text
        for marker in ("回复", "答案", "输出", "交付", "answer", "response")
    ):
        return None
    matches = re.findall(r"[“\"]([^”\"]{1,500})[”\"]", text)
    if not matches:
        return None
    candidate = matches[-1].strip()
    return candidate or None


def _render_final_summary(
    *,
    task: str,
    rounds,
    decision: SupervisorDecision,
    generic_approach: GenericApproach | None = None,
) -> str:
    lines = [
        f"# Supervisor Summary",
        "",
        f"- Task: {task}",
        f"- Decision: {decision.decision}",
        f"- Reason: {decision.reason}",
        "",
        "## Rounds",
    ]
    if generic_approach is not None:
        lines.insert(5, f"- Generic approach: {generic_approach}")
    for round_result in rounds:
        lines.append(
            f"- Round {round_result.graph.round_index}: "
            f"{round_result.completed_count} completed, "
            f"{round_result.failed_count} failed, "
            f"{round_result.blocked_count} blocked, "
            f"{round_result.partial_count} partial"
        )
        for item in round_result.node_results:
            lines.append(f"  - {item.node_id}: {item.status} - {item.summary}")
    return "\n".join(lines) + "\n"


def _materialize_benchmark_operator_products(
    *,
    run_dir: Path,
    selected_tools: list[str],
    source_repo: str,
) -> list[str]:
    """Write manifest-first operator products for benchmark cases.

    The file manifests are canonical; the SQLite database below
    ``operator_store/`` is a rebuildable query layer.
    """
    artifacts: list[str] = []
    if not selected_tools:
        return artifacts
    store = OperatorStore(_operator_store_root_for_run_dir(run_dir))
    for repo in selected_tools:
        case_dir = run_dir / "cases" / repo
        manifest_path = case_dir / "manifest.json"
        ready_path = case_dir / "execution_ready.json"
        if not (manifest_path.exists() and ready_path.exists()):
            continue
        try:
            case_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            ready_payload = json.loads(ready_path.read_text(encoding="utf-8"))
            status, validation_summary = _benchmark_operator_status(
                repo=repo,
                case_dir=case_dir,
                ready_payload=ready_payload,
            )
            product_id = f"benchmark:{repo}:{run_dir.name}"
            product_dir = store.product_dir(
                family="benchmark",
                name=repo,
                version=run_dir.name,
            )
            product_manifest = build_benchmark_operator_manifest(
                product_id=product_id,
                name=repo,
                version=run_dir.name,
                run_dir=run_dir,
                case_dir=case_dir,
                case_manifest=case_manifest,
                ready_payload=ready_payload,
                status=status,
                validation_summary=validation_summary,
                source_repo=source_repo,
            )
            written = store.write_manifest(product_manifest, product_dir=product_dir)
        except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
            failure_path = case_dir / "operator_product_error.json"
            _write_json(
                failure_path,
                {
                    "repo": repo,
                    "error": str(exc),
                    "run_dir": str(run_dir),
                },
            )
            artifacts.append(str(failure_path))
            continue
        artifacts.append(str(written))
    if artifacts:
        artifacts.append(str(store.db_path))
    return artifacts


def _materialize_github2workspace_operator_product(
    *,
    task: str,
    workspace_root: Path,
    run_dir: Path,
    rounds: list[Any],
    final_decision: SupervisorDecision,
) -> Path | None:
    repo_name = _github2workspace_product_name(task=task, workspace_root=workspace_root)
    if not repo_name:
        return None
    source_repo = _github_url_from_task(task) or ""
    status = _github2workspace_product_status(
        workspace_root=workspace_root,
        rounds=rounds,
        final_decision=final_decision,
    )
    summary = _github2workspace_validation_summary(rounds=rounds, status=status)
    store = OperatorStore(_operator_store_root_for_run_dir(run_dir))
    manifest = build_github2workspace_operator_manifest(
        product_id=f"github2workspace:{repo_name}:{run_dir.name}",
        name=repo_name,
        version=run_dir.name,
        workspace_root=workspace_root,
        run_dir=run_dir,
        status=status,
        source_repo=source_repo,
        validation_summary=summary,
        evaluation=_github2workspace_evaluation_payload(run_dir),
    )
    try:
        return store.write_manifest(
            manifest,
            product_dir=store.product_dir(
                family="github2workspace",
                name=repo_name,
                version=run_dir.name,
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        _write_json(
            run_dir / "operator_product_error.json",
            {
                "task": task,
                "repo_name": repo_name,
                "error": str(exc),
            },
        )
        return None


def _github2workspace_evaluation_payload(run_dir: Path) -> dict[str, object]:
    evaluation_path = run_dir / "evaluation.json"
    try:
        payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _github2workspace_product_name(*, task: str, workspace_root: Path) -> str | None:
    url = _github_url_from_task(task)
    if url:
        name = url.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        if name:
            return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or None
    dockerfiles = sorted(workspace_root.glob("*_Dockerfile"))
    if dockerfiles:
        return dockerfiles[0].name.removesuffix("_Dockerfile")
    return None


def _github_url_from_task(task: str) -> str | None:
    match = re.search(r"https://github\.com/[^\s，。'\"`]+", task)
    if not match:
        return None
    return match.group(0).rstrip(".,;)")


def _github2workspace_product_status(
    *,
    workspace_root: Path,
    rounds: list[Any],
    final_decision: SupervisorDecision,
) -> str:
    wdl_outputs = workspace_root / "results" / "wdl_result" / "outputs.json"
    uses_synthetic_inputs = _github2workspace_uses_synthetic_inputs(
        workspace_root=workspace_root
    )
    if (
        wdl_outputs.exists()
        and wdl_outputs.stat().st_size > 0
        and not uses_synthetic_inputs
    ):
        return "completed"
    build_completed = _node_status_seen(
        rounds=rounds, node_id="build", status="completed"
    )
    docker_outputs = list(
        (workspace_root / "results" / "docker_test").glob("**/contigs.fasta")
    )
    if build_completed and docker_outputs:
        return "docker_validated"
    if uses_synthetic_inputs:
        return "partial"
    if final_decision.failed_nodes:
        return "partial"
    return "registered"


def _node_status_seen(*, rounds: list[Any], node_id: str, status: str) -> bool:
    for round_result in rounds:
        for result in getattr(round_result, "node_results", []):
            if result.node_id == node_id and result.status == status:
                return True
    return False


def _github2workspace_validation_summary(*, rounds: list[Any], status: str) -> str:
    summaries: list[str] = []
    for round_result in rounds:
        for result in getattr(round_result, "node_results", []):
            if result.node_id in {"inspect", "build", "wdl", "retry_wdl", "summarize"}:
                summaries.append(f"{result.node_id}:{result.status}: {result.summary}")
    text = "\n".join(summaries)
    if len(text) > 4000:
        text = text[:4000] + "\n... truncated"
    return f"status={status}\n{text}"


def _github2workspace_uses_synthetic_inputs(*, workspace_root: Path) -> bool:
    inputs_json = workspace_root / "inputs.json"
    if not inputs_json.exists():
        return False
    try:
        payload = json.loads(inputs_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(payload, dict):
        return False
    for value in payload.values():
        if not isinstance(value, str):
            continue
        lowered = value.casefold()
        if any(marker in lowered for marker in ("toy", "synthetic", "generated")):
            return True
        if "/results/wdl_file/" in lowered and lowered.endswith(
            (".fastq", ".fq", ".fasta", ".fa")
        ):
            return True
    return False


def _benchmark_operator_status(
    *,
    repo: str,
    case_dir: Path,
    ready_payload: dict[str, object],
) -> tuple[str, str]:
    status_path = case_dir / "run" / "status.json"
    if status_path.exists():
        try:
            status_payload = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return "failed", f"{repo} has an unreadable run/status.json."
        if status_payload.get("success") is True:
            result_manifest_path = case_dir / "run" / "result_manifest.json"
            if result_manifest_path.exists():
                try:
                    result_manifest = json.loads(
                        result_manifest_path.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    result_manifest = {}
                expected_outputs = result_manifest.get("expected_outputs")
                if isinstance(expected_outputs, dict) and expected_outputs:
                    if any(
                        isinstance(item, dict) and item.get("exists") is True
                        for item in expected_outputs.values()
                    ):
                        return (
                            "completed",
                            f"{repo} ran successfully and produced expected output evidence.",
                        )
                    return (
                        "partial",
                        f"{repo} ran successfully, but expected output files were not found.",
                    )
            return "completed", f"{repo} ran successfully."
        reason = _optional_str(status_payload.get("failure_reason")) or "run_failed"
        return "failed", f"{repo} execution failed: {reason}."
    if ready_payload.get("ready") is True:
        return "registered_ready", f"{repo} is registered and execution-ready."
    blockers = []
    for key in ("missing", "blockers", "failure_reason", "reason"):
        value = ready_payload.get(key)
        if isinstance(value, list):
            blockers.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            blockers.append(value.strip())
    if not blockers:
        if not ready_payload.get("runtime_image"):
            blockers.append("missing_runtime_image")
        if not ready_payload.get("wdl_path"):
            blockers.append("missing_wdl_path")
        if not ready_payload.get("inputs_json_path"):
            blockers.append("missing_inputs_json_path")
    return (
        "blocked",
        f"{repo} is not execution-ready: {', '.join(blockers) or 'unknown blocker'}.",
    )


def _operator_store_root_for_run_dir(run_dir: Path) -> Path:
    if run_dir.parent.name == "orchestration_runs":
        return run_dir.parent.parent / "operator_store"
    return run_dir.parent / "operator_store"


def _benchmark_result_store_root_for_run_dir(run_dir: Path) -> Path:
    if run_dir.parent.name == "orchestration_runs":
        return run_dir.parent.parent / _BENCHMARK_COMPARISON_HISTORY_STORE_DIR
    return run_dir.parent / _BENCHMARK_COMPARISON_HISTORY_STORE_DIR


def _ensure_workspace_benchmark_history_backfilled(workspace_root: Path) -> list[Path]:
    target_root = (workspace_root / _BENCHMARK_COMPARISON_HISTORY_STORE_DIR).resolve()
    if target_root in _BENCHMARK_HISTORY_BACKFILL_ATTEMPTED:
        return []
    _BENCHMARK_HISTORY_BACKFILL_ATTEMPTED.add(target_root)
    if _history_store_has_records(target_root):
        return []
    return _backfill_workspace_benchmark_history(
        workspace_root=workspace_root, store_root=target_root
    )


def _history_store_has_records(store_root: Path) -> bool:
    records_dir = store_root / "records"
    if not records_dir.exists():
        return False
    return any(records_dir.glob(f"**/{BENCHMARK_RECORD_NAME}"))


def _backfill_workspace_benchmark_history(
    *,
    workspace_root: Path,
    store_root: Path,
) -> list[Path]:
    written: list[Path] = []
    for run_dir in _discover_workspace_benchmark_run_dirs(workspace_root):
        root_manifest = _read_json_file(run_dir / "manifest.json")
        if not isinstance(root_manifest, dict):
            continue
        case_order = root_manifest.get("case_order", [])
        if not isinstance(case_order, list):
            continue
        for repo_value in case_order:
            repo = str(repo_value).strip()
            if not repo:
                continue
            record_path = _backfill_benchmark_history_record_for_case(
                workspace_root=workspace_root,
                store_root=store_root,
                run_dir=run_dir,
                repo=repo,
            )
            if record_path is not None:
                written.append(record_path)
    return written


def _discover_workspace_benchmark_run_dirs(workspace_root: Path) -> list[Path]:
    discovered: list[Path] = []
    seen: set[Path] = set()
    for root, dirnames, filenames in os.walk(workspace_root, topdown=True):
        dirnames[:] = [
            name for name in dirnames if name != _BENCHMARK_COMPARISON_HISTORY_STORE_DIR
        ]
        if "cases" not in dirnames or "manifest.json" not in filenames:
            continue
        run_dir = Path(root)
        try:
            resolved = run_dir.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        discovered.append(resolved)
        if "cases" in dirnames:
            dirnames.remove("cases")
    discovered.sort(
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True
    )
    return discovered


def _backfill_benchmark_history_record_for_case(
    *,
    workspace_root: Path,
    store_root: Path,
    run_dir: Path,
    repo: str,
) -> Path | None:
    if (
        store_root.resolve()
        == _benchmark_result_store_root_for_run_dir(run_dir).resolve()
    ):
        existing_record = (
            store_root
            / "records"
            / _safe_benchmark_store_part(repo)
            / _safe_benchmark_store_part(run_dir.name)
            / BENCHMARK_RECORD_NAME
        )
        if existing_record.exists():
            return existing_record
    case_dir = run_dir / "cases" / repo
    manifest = _read_json_file(case_dir / "manifest.json")
    if not isinstance(manifest, dict):
        return None
    run_status = _read_json_file(case_dir / "run" / "status.json")
    wdl_status = _read_json_file(case_dir / "wdl" / "status.json")
    status_payload: dict[str, object] | None = None
    if isinstance(run_status, dict):
        status_payload = dict(run_status)
    elif isinstance(wdl_status, dict):
        status_payload = _benchmark_status_payload_from_wdl_status(
            repo=repo,
            case_dir=case_dir,
            wdl_status=wdl_status,
        )
        (case_dir / "run").mkdir(parents=True, exist_ok=True)
        _write_json(case_dir / "run" / "status.json", status_payload)
    if status_payload is None:
        return None
    result_manifest_path = case_dir / "run" / "result_manifest.json"
    result_manifest = _read_json_file(result_manifest_path)
    if not isinstance(result_manifest, dict):
        result_manifest = _write_benchmark_result_manifest(
            repo=repo,
            case_dir=case_dir,
            status_payload=status_payload,
        )
    if not (case_dir / "analysis.json").exists():
        return None
    return _materialize_benchmark_result_record_to_store(
        repo=repo,
        run_dir=run_dir,
        case_dir=case_dir,
        manifest=manifest,
        status_payload=status_payload,
        result_manifest=result_manifest,
        store_root=store_root,
    )


def _benchmark_status_payload_from_wdl_status(
    *,
    repo: str,
    case_dir: Path,
    wdl_status: dict[str, object],
) -> dict[str, object]:
    wdl_output_dir = case_dir / "wdl" / "run_outputs"
    output_dir_raw = wdl_status.get("output_dir")
    if isinstance(output_dir_raw, str) and output_dir_raw.strip():
        wdl_output_dir = Path(output_dir_raw.strip())
    copied_artifacts = [
        str(path)
        for path in _benchmark_expected_output_paths(
            repo=repo,
            case_dir=case_dir,
            status_payload={
                "output_dir": str(wdl_output_dir),
                "output_artifacts": wdl_status.get("output_artifacts", []),
            },
        )
        if path.exists()
    ]
    if not copied_artifacts:
        copied_artifacts = [
            str(Path(str(artifact)))
            for artifact in wdl_status.get("output_artifacts", [])
            if isinstance(artifact, str) and Path(artifact).exists()
        ]
    return {
        "attempted": True,
        "completed": True,
        "success": bool(wdl_status.get("success")),
        "returncode": wdl_status.get("returncode"),
        "started_at": wdl_status.get("started_at"),
        "finished_at": wdl_status.get("finished_at"),
        "elapsed_seconds": wdl_status.get("elapsed_seconds"),
        "command": ["run-wdl", repo],
        "log_path": wdl_status.get("log_path"),
        "output_dir": str(wdl_output_dir),
        "output_artifacts": copied_artifacts,
        "failure_reason": wdl_status.get("failure_reason"),
        "execution_mode": "wdl_only",
    }


def _safe_benchmark_store_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return normalized.strip("-") or "unknown"


def _write_metric_plan(
    *, run_dir: Path, selected_tools: list[str]
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    shared_datasets: list[str] = []
    for repo in selected_tools:
        manifest = json.loads(
            (run_dir / "cases" / repo / "manifest.json").read_text(encoding="utf-8")
        )
        dataset_key = str(manifest.get("dataset_key", ""))
        if dataset_key and dataset_key not in shared_datasets:
            shared_datasets.append(dataset_key)
        rows.append(
            {
                "repo": repo,
                "dataset_key": dataset_key,
                "metric_keys": [str(item) for item in manifest.get("metric_keys", [])],
                "selected_input_files": manifest.get("selected_input_files", {}),
            }
        )
    payload = {
        "run_dir": str(run_dir),
        "selected_tools": selected_tools,
        "shared_datasets": shared_datasets,
        "rows": rows,
    }
    _write_json(run_dir / "metric_plan.json", payload)
    lines = [
        "# Metric Plan",
        "",
        f"- run_dir: `{run_dir}`",
        f"- selected_tools: `{', '.join(selected_tools)}`",
        f"- shared_datasets: `{', '.join(shared_datasets) if shared_datasets else 'none'}`",
        "",
        "## Rows",
        "",
    ]
    lines.extend(
        f"- `{row['repo']}` -> dataset `{row['dataset_key']}`, metrics `{', '.join(row['metric_keys'])}`"
        for row in rows
    )
    (run_dir / "metric_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def _locate_repo_root_for_benchmark(
    *, node: TaskNode, workspace_root: Path
) -> Path | None:
    task = str(node.metadata.get("task", "")) if isinstance(node.metadata, dict) else ""
    for match in _TASK_PATH_RE.finditer(task):
        candidate = Path(match.group(1).rstrip("。.,)"))
        repo_root = _walk_to_repo_root(candidate)
        if repo_root is not None:
            return repo_root
    if workspace_root.parent.name == "workspace":
        repo_root = _walk_to_repo_root(workspace_root.parent.parent)
        if repo_root is not None:
            return repo_root
    return _walk_to_repo_root(Path(__file__).resolve().parents[3])


def _run_helper_json_command(
    command: list[str],
    *,
    cwd: Path,
    phase: str,
) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"{phase} exited with code {completed.returncode}: {stderr or stdout or 'no output'}"
        )
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{phase} returned non-JSON output: {stdout or stderr}"
        ) from exc
    return {
        "phase": phase,
        "command": command,
        "stdout": payload,
    }


def _walk_to_repo_root(candidate: Path) -> Path | None:
    start = candidate if candidate.is_dir() else candidate.parent
    for path in (start, *start.parents):
        if (path / ".code2workspace").exists() or (path / ".git").exists():
            return path
    return None


def _discover_run_dirs(workspace_root: Path) -> list[Path]:
    candidates = set(workspace_root.glob("orchestration_runs/*"))
    candidates.update(workspace_root.glob("*/orchestration_runs/*"))
    return sorted(path for path in candidates if path.is_dir())


def _case_collection_root(workspace_root: Path) -> Path:
    if workspace_root.parent.name == "workspace":
        return workspace_root.parent
    return workspace_root


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_github_repo_materialization_log(
    path: Path, payload: dict[str, object]
) -> None:
    _write_json(path, payload)


def _optional_path(value: object) -> Path | None:
    rendered = _optional_str(value)
    if rendered is None:
        return None
    return Path(rendered)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_.-]+", text.casefold())


def _latest_human_text(state: dict[str, object]) -> str | None:
    messages = state.get("messages") or []
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if getattr(message, "type", None) != "human":
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
        rendered = str(content).strip()
        if rendered:
            return rendered
    return None


def _latest_human_requests_execution(state: dict[str, object]) -> bool:
    """Return whether the latest user message explicitly starts execution."""
    latest = _latest_human_text(state)
    if not latest:
        return False
    text = re.sub(r"\s+", " ", latest.strip().casefold())
    if not text:
        return False
    negative_markers = (
        "不要执行",
        "不要开始",
        "先不执行",
        "先别执行",
        "暂不执行",
        "暂时不执行",
        "不用执行",
        "别开始",
        "别执行",
        "不要跑",
        "先不跑",
        "not yet",
        "do not execute",
        "don't execute",
        "do not start",
        "don't start",
        "not start",
    )
    if any(marker in text for marker in negative_markers):
        return False

    direct_patterns = (
        r"开始执行",
        r"开始跑",
        r"开始运行",
        r"执行任务",
        r"跑任务",
        r"执行吧",
        r"开始吧",
        r"跑吧",
        r"按.*方案.*(执行|开始|跑|做)",
        r"照.*方案.*(执行|开始|跑|做)",
        r"按.*计划.*(执行|开始|跑|做)",
        r"可以.*(开始|执行|跑)",
        r"没问题.*(开始|执行|跑)",
        r"同意.*(开始|执行|跑)",
        r"确认.*(开始|执行|跑)",
        r"\b(go ahead|start|execute|run it|proceed)\b",
    )
    if any(re.search(pattern, text) for pattern in direct_patterns):
        return True

    if not _last_ai_asked_for_execution_confirmation(state):
        return False
    affirmative_replies = {
        "可以",
        "可以了",
        "好",
        "好的",
        "行",
        "行的",
        "没问题",
        "确认",
        "同意",
        "就这样",
        "按这个来",
        "按方案来",
        "yes",
        "ok",
        "okay",
        "sure",
    }
    return text in affirmative_replies


def _last_ai_asked_for_execution_confirmation(state: dict[str, object]) -> bool:
    messages = state.get("messages") or []
    if not isinstance(messages, list):
        return False
    return _INTERACTIVE_CONFIRMATION_FOOTER in _last_ai_text(messages)


async def _render_interactive_execution_proposal(
    *,
    state: dict[str, object],
    proposal_model: Any | None,
) -> str:
    """Render a no-tools interactive proposal before Supervisor execution."""
    prompt = _interactive_proposal_user_prompt(state)
    text = ""
    if proposal_model is not None:
        try:
            response = await proposal_model.ainvoke(
                [
                    SystemMessage(content=_INTERACTIVE_PROPOSAL_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
            text = _message_text(response)
        except Exception:
            logger.debug(
                "Interactive proposal model failed; using deterministic fallback.",
                exc_info=True,
            )
    if not text.strip():
        task = _latest_human_text(state) or "这次任务"
        text = (
            "我先把你的意图整理成一个待确认方案：\n\n"
            f"1. 明确目标：{task}\n"
            "2. 先按任务需要规划步骤和产物。\n"
            "3. 你确认后，我再进入自动执行阶段并持续跑到完成。"
        )
    return _ensure_interactive_confirmation_footer(text)


def _interactive_proposal_user_prompt(state: dict[str, object]) -> str:
    messages = state.get("messages") or []
    transcript = _recent_dialogue_text(messages if isinstance(messages, list) else [])
    latest = _latest_human_text(state) or ""
    return (
        "请根据下面最近对话，整理一个用户确认后才会执行的方案。"
        "当前不要执行。\n\n"
        f"最新用户输入：\n{latest}\n\n"
        f"最近对话：\n{transcript}"
    )


def _confirmed_interactive_execution_task(state: dict[str, object]) -> str | None:
    latest = _latest_human_text(state)
    if not latest:
        return None
    if not _latest_human_requests_execution(state):
        return latest
    messages = state.get("messages") or []
    if not isinstance(messages, list):
        return latest
    prior_human = _recent_human_texts_before_latest(messages, limit=6)
    plan = _strip_interactive_confirmation_footer(_last_ai_text(messages))
    if not prior_human and not plan:
        return latest
    parts = [
        "用户已明确确认开始执行。请把下面内容作为一个非交互式任务自动完成，直到产出最终结果。",
        "",
    ]
    if prior_human:
        parts.append("原始和修订意图：")
        parts.extend(f"- {item}" for item in prior_human)
        parts.append("")
    if plan:
        parts.append("已确认方案：")
        parts.append(plan)
        parts.append("")
    parts.append("用户确认消息：")
    parts.append(latest)
    return "\n".join(parts).strip()


def _ensure_interactive_confirmation_footer(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return _INTERACTIVE_CONFIRMATION_FOOTER
    without_footer = _strip_interactive_confirmation_footer(stripped).rstrip()
    return f"{without_footer}\n\n{_INTERACTIVE_CONFIRMATION_FOOTER}"


def _strip_interactive_confirmation_footer(text: str) -> str:
    stripped = text.strip()
    if stripped.endswith(_INTERACTIVE_CONFIRMATION_FOOTER):
        return stripped[: -len(_INTERACTIVE_CONFIRMATION_FOOTER)].rstrip()
    return stripped


def _recent_dialogue_text(messages: list[Any], *, limit: int = 10) -> str:
    lines: list[str] = []
    for message in messages[-limit:]:
        role = str(getattr(message, "type", "") or "")
        if role not in {"human", "ai"}:
            continue
        text = _message_content_text(getattr(message, "content", ""))
        if not text:
            continue
        label = "用户" if role == "human" else "助手"
        lines.append(f"{label}: {text}")
    return "\n".join(lines) or "(无可用上下文)"


def _recent_human_texts_before_latest(
    messages: list[Any],
    *,
    limit: int,
) -> list[str]:
    humans: list[str] = []
    for message in messages:
        if getattr(message, "type", None) != "human":
            continue
        text = _message_content_text(getattr(message, "content", ""))
        if text:
            humans.append(text)
    if not humans:
        return []
    return humans[:-1][-limit:]


def _message_content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part.strip() for part in parts if part and part.strip())
    rendered = str(content).strip()
    return rendered if rendered else ""


def _latest_human_route_mode(state: dict[str, object]) -> str | None:
    """Return any explicit routing override stored on the latest human message."""
    messages = state.get("messages") or []
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if getattr(message, "type", None) != "human":
            continue
        additional_kwargs = getattr(message, "additional_kwargs", None)
        if not isinstance(additional_kwargs, dict):
            return None
        route = additional_kwargs.get("epimindagent_route")
        if route is None:
            route = additional_kwargs.get("code2workspace_route")
        if isinstance(route, str) and route.strip():
            return route.strip().lower()
        return None
    return None
