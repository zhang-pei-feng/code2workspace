"""Supervisor graph planning and execution primitives."""

from __future__ import annotations

import asyncio
import ast
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.errors import GraphBubbleUp

CapabilityBundle = Literal[
    "repo_fetch",
    "docker_build_run",
    "wdl_run",
    "data_filter",
    "operator_filter",
    "metric_compute",
    "summarize",
    "validate",
    "plan",
    "task_manage",
    "web_search",
    "web_fetch",
    "db_access",
    "api_call",
]

TaskType = Literal["generic", "github2workspace", "benchmark", "report"]
WorkerStatus = Literal["completed", "blocked", "failed", "partial"]
DecisionType = Literal["stop", "replan", "continue"]
GenericApproach = Literal["simple", "medium", "difficult"]

@dataclass(slots=True)
class TaskNode:
    node_id: str
    title: str
    objective: str
    capability_bundles: list[CapabilityBundle]
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class TaskEdge:
    source: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class TaskGraph:
    graph_id: str
    task_type: TaskType
    round_index: int
    nodes: list[TaskNode]
    edges: list[TaskEdge]
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "graph_id": self.graph_id,
            "task_type": self.task_type,
            "round_index": self.round_index,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class WorkerTaskEnvelope:
    node: TaskNode
    round_index: int
    workspace_dir: str
    recursion_depth: int
    recursion_budget: int

    def to_dict(self) -> dict[str, object]:
        return {
            "node": self.node.to_dict(),
            "round_index": self.round_index,
            "workspace_dir": self.workspace_dir,
            "recursion_depth": self.recursion_depth,
            "recursion_budget": self.recursion_budget,
        }


@dataclass(slots=True)
class WorkerResult:
    status: WorkerStatus
    summary: str
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    next_action_hint: str | None = None
    failure_reason: str | None = None
    spawned_subgraph: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class WorkerNodeResult:
    node_id: str
    status: WorkerStatus
    summary: str
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    next_action_hint: str | None = None
    failure_reason: str | None = None
    spawned_subgraph: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class TaskExecutionRound:
    graph: TaskGraph
    node_results: list[WorkerNodeResult]

    @property
    def completed_count(self) -> int:
        return sum(item.status == "completed" for item in self.node_results)

    @property
    def failed_count(self) -> int:
        return sum(item.status == "failed" for item in self.node_results)

    @property
    def blocked_count(self) -> int:
        return sum(item.status == "blocked" for item in self.node_results)

    @property
    def partial_count(self) -> int:
        return sum(item.status == "partial" for item in self.node_results)

    def to_dict(self) -> dict[str, object]:
        return {
            "graph": self.graph.to_dict(),
            "node_results": [item.to_dict() for item in self.node_results],
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "blocked_count": self.blocked_count,
            "partial_count": self.partial_count,
        }


@dataclass(slots=True)
class SupervisorDecision:
    decision: DecisionType
    reason: str
    failed_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class CaseTraceRecord:
    task_type: str
    summary: str
    run_dir: str | None = None
    score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class CaseIndexEntry:
    task: str
    task_type: str
    summary: str
    run_dir: str
    score: float = 0.0

    def to_case_trace_record(self) -> CaseTraceRecord:
        return CaseTraceRecord(
            task_type=self.task_type,
            summary=self.summary,
            run_dir=self.run_dir,
            score=self.score,
        )


@dataclass(frozen=True, slots=True)
class TaskGuidance:
    """Experience guidance for a known task family."""

    guidance_id: str
    task_type: TaskType
    markers: tuple[str, ...]
    summary: str


@dataclass(slots=True)
class TaskClassification:
    """Planner-facing task classification."""

    primary_type: TaskType
    guidance_ids: list[str]


_SPECIAL_TASK_TYPES = {"benchmark", "github2workspace", "report", "generic"}
_TASK_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.55
_TASK_CLASSIFIER_SYSTEM_PROMPT = """You classify a user task for a supervisor runtime.

Choose exactly one task_type from:
- benchmark
- github2workspace
- report
- generic

Definitions:
- benchmark: compare tools or workflows on shared datasets and summarize metrics or results
- github2workspace: turn a repository into a runnable workspace, usually involving repository inspection, Docker, validation, WDL, or Cromwell
- report: write a formal evidence-backed report, risk assessment, monitoring brief, or synthesis
- generic: anything else

Important disambiguation rules:
- If the task is primarily about fixing code in a single repository, producing a patch, or satisfying one or more repo-local tests, classify it as generic even if the prompt contains words like "benchmark", "FAIL_TO_PASS", "instance_id", "hints", or copied benchmark metadata.
- Only classify as benchmark when the task is actually asking to compare multiple tools, workflows, or configurations on shared datasets and then summarize metrics, outcomes, or scorecards.
- A software-repair task wrapped in benchmark-style metadata is still generic unless it explicitly asks for cross-tool evaluation or metric comparison.
- Only classify as report when the user is asking for a formal deliverable such as a report, brief, formal assessment, presentation-ready writeup, or WHO-style structured synthesis.
- If the user explicitly asks for a quick analysis, oral judgment, direct answer, normal discussion, or says things like "不要正式写作", "先给我一个口头判断", or "区分证据和猜测", classify as generic unless the prompt still clearly demands a formal report artifact.

Return JSON only with keys:
{
  "task_type": "...",
  "confidence": 0.0,
  "reason": "...",
  "matched_signals": ["..."]
}
"""


_TASK_GUIDANCE_REGISTRY: tuple[TaskGuidance, ...] = (
    TaskGuidance(
        guidance_id="benchmark_family",
        task_type="benchmark",
        markers=("benchmark", "workflow comparison", "组装 benchmark", "staged benchmark"),
        summary="Use staged registration, per-tool fan-out, metrics aggregation, and retry failed tools before summarizing.",
    ),
    TaskGuidance(
        guidance_id="github2workspace_pipeline",
        task_type="github2workspace",
        markers=("github.com/", "github2workspace", "可运行 workspace", "runnable workspace"),
        summary="Use inspect -> build -> workflow validation -> summarize, and replan from the first failed phase.",
    ),
    TaskGuidance(
        guidance_id="report_synthesis",
        task_type="report",
        markers=("报告", "风险评估", "monitoring brief", "risk assessment", "formal report", "who 风格"),
        summary="Use init -> parallel evidence lanes -> compose -> summarize, preserving evidence layers and uncertainty.",
    ),
)

_GENERIC_FORMAL_NEGATIVE_MARKERS = (
    "不要正式写作",
    "口头判断",
    "直接说",
    "直接回答",
    "先帮我分析",
    "区分证据和猜测",
)


def classify_task(task: str) -> TaskClassification:
    """Classify a task and attach any matched guidance ids."""

    lowered = task.casefold()
    if any(marker.casefold() in lowered for marker in _GENERIC_FORMAL_NEGATIVE_MARKERS):
        return TaskClassification(primary_type="generic", guidance_ids=[])
    guidance_ids: list[str] = []
    primary_type: TaskType = "generic"
    for guidance in _TASK_GUIDANCE_REGISTRY:
        if any(marker.casefold() in lowered for marker in guidance.markers):
            guidance_ids.append(guidance.guidance_id)
            if primary_type == "generic":
                primary_type = guidance.task_type
    return TaskClassification(primary_type=primary_type, guidance_ids=guidance_ids)


def detect_task_type(task: str) -> TaskType:
    return classify_task(task).primary_type


async def classify_task_with_model(
    *,
    model,
    task: str,
) -> tuple[TaskClassification, dict[str, Any]]:
    """Use an LLM to classify the main task family, then fall back to rules."""

    rule_classification = classify_task(task)
    rule_details: dict[str, Any] = {
        "source": "rules_fallback",
        "task_type": rule_classification.primary_type,
        "guidance_ids": list(rule_classification.guidance_ids),
    }
    if model is None or not task.strip():
        return rule_classification, rule_details

    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=_TASK_CLASSIFIER_SYSTEM_PROMPT),
                HumanMessage(content=f"Task:\n{task}\n\nReturn JSON only."),
            ]
        )
    except Exception as exc:
        rule_details["llm_error"] = f"{type(exc).__name__}: {exc}"
        return rule_classification, rule_details

    text = _message_text(response)
    payload = _extract_task_classifier_payload(text)
    if payload is None:
        rule_details["llm_error"] = "invalid_classifier_output"
        rule_details["raw_output"] = text
        return rule_classification, rule_details

    task_type = payload.get("task_type")
    confidence = payload.get("confidence")
    reason = payload.get("reason")
    matched_signals = payload.get("matched_signals")
    if (
        not isinstance(task_type, str)
        or task_type not in _SPECIAL_TASK_TYPES
        or not isinstance(confidence, (int, float))
        or float(confidence) < _TASK_CLASSIFIER_CONFIDENCE_THRESHOLD
    ):
        rule_details["llm_candidate"] = {
            "task_type": task_type,
            "confidence": confidence,
            "reason": reason,
            "matched_signals": matched_signals,
        }
        rule_details["llm_error"] = "low_confidence_or_invalid_task_type"
        return rule_classification, rule_details

    llm_classification = classification_for_task_type(task_type)
    return llm_classification, {
        "source": "llm_classifier",
        "task_type": llm_classification.primary_type,
        "guidance_ids": list(llm_classification.guidance_ids),
        "confidence": float(confidence),
        "reason": str(reason) if isinstance(reason, str) else "",
        "matched_signals": [
            str(item)
            for item in matched_signals
            if isinstance(matched_signals, list)
            for item in matched_signals
        ],
        "rules_fallback_task_type": rule_classification.primary_type,
    }


def classification_for_task_type(task_type: TaskType) -> TaskClassification:
    """Build a classification object from an explicit task type."""

    guidance_ids = [
        guidance.guidance_id
        for guidance in _TASK_GUIDANCE_REGISTRY
        if guidance.task_type == task_type
    ]
    return TaskClassification(primary_type=task_type, guidance_ids=guidance_ids)


def _message_text(response: object) -> str:
    if isinstance(response, AIMessage):
        content = response.content
        if isinstance(content, str):
            return content
        return str(content)
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rendered = "\n".join(str(item) for item in content if str(item).strip())
        if rendered.strip():
            return rendered
    return str(response)


def _extract_task_classifier_payload(text: str) -> dict[str, Any] | None:
    payload = _extract_json_object(text)
    if payload is None:
        return None
    return _extract_payload_from_object(payload)


def _extract_json_object(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_payload_from_object(payload: object) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        task_type = payload.get("task_type")
        confidence = payload.get("confidence")
        if isinstance(task_type, str) and isinstance(confidence, (int, float)):
            return payload
        text_value = payload.get("text")
        if isinstance(text_value, str):
            nested = _extract_json_object(text_value)
            if nested is not None:
                return _extract_payload_from_object(nested)
        content_value = payload.get("content")
        if isinstance(content_value, str):
            nested = _extract_json_object(content_value)
            if nested is not None:
                return _extract_payload_from_object(nested)
        return None
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_payload_from_object(item)
            if nested is not None:
                return nested
    return None


class HeuristicSupervisorPlanner:
    """Build graph rounds for all tasks; known families add guidance/templates."""

    def plan_round(
        self,
        *,
        task: str,
        retrieved_cases: list[CaseTraceRecord],
        prior_rounds: list[TaskExecutionRound],
        generic_approach: GenericApproach | None = None,
        classification_override: TaskClassification | None = None,
    ) -> TaskGraph:
        classification = classification_override or classify_task(task)
        round_index = len(prior_rounds) + 1
        if classification.primary_type == "github2workspace":
            return self._plan_github2workspace(
                task=task,
                retrieved_cases=retrieved_cases,
                prior_rounds=prior_rounds,
                round_index=round_index,
                guidance_ids=classification.guidance_ids,
            )
        if classification.primary_type == "benchmark":
            return self._plan_benchmark(
                task=task,
                retrieved_cases=retrieved_cases,
                prior_rounds=prior_rounds,
                round_index=round_index,
                guidance_ids=classification.guidance_ids,
            )
        if classification.primary_type == "report":
            return self._plan_report(
                task=task,
                retrieved_cases=retrieved_cases,
                prior_rounds=prior_rounds,
                round_index=round_index,
                guidance_ids=classification.guidance_ids,
            )
        return self._plan_generic(
            task=task,
            retrieved_cases=retrieved_cases,
            prior_rounds=prior_rounds,
            round_index=round_index,
            guidance_ids=classification.guidance_ids,
            generic_approach=generic_approach,
        )

    def _plan_generic(
        self,
        *,
        task: str,
        retrieved_cases: list[CaseTraceRecord],
        prior_rounds: list[TaskExecutionRound],
        round_index: int,
        guidance_ids: list[str],
        generic_approach: GenericApproach | None,
    ) -> TaskGraph:
        if not prior_rounds:
            nodes = [
                TaskNode(
                    node_id="init_generic",
                    title="Initialize generic run",
                    objective="Create the generic task context, restate the delivery contract, identify 2-3 bounded worker units, and write a batch plan for one parallel execution layer.",
                    capability_bundles=["plan", "task_manage", "validate"],
                ),
                TaskNode(
                    node_id="worker_context",
                    title="Context and evidence worker",
                    objective="Handle one bounded generic work unit focused on constraints, evidence, repository facts, or source-backed context needed for the task.",
                    capability_bundles=["repo_fetch", "web_search", "web_fetch", "db_access", "api_call", "validate"],
                    metadata={"worker_role": "context"},
                ),
                TaskNode(
                    node_id="worker_solution",
                    title="Solution and execution worker",
                    objective="Handle one bounded generic work unit focused on implementation, execution, repair, or solution design needed for the task.",
                    capability_bundles=[
                        "repo_fetch",
                        "docker_build_run",
                        "wdl_run",
                        "data_filter",
                        "operator_filter",
                        "metric_compute",
                        "validate",
                    ],
                    metadata={"worker_role": "solution"},
                ),
                TaskNode(
                    node_id="compose_generic",
                    title="Compose generic answer",
                    objective="Merge the worker notes into one normal long-form user-facing answer, preserving uncertainty without turning the result into a formal report artifact.",
                    capability_bundles=["summarize", "validate"],
                ),
                TaskNode(
                    node_id="summarize",
                    title="Summarize generic outcome",
                    objective="Summarize the strongest verified generic outcome, worker contributions, blockers, and next-step recommendation.",
                    capability_bundles=["summarize"],
                ),
            ]
            edges = [
                TaskEdge(source="init_generic", target="worker_context"),
                TaskEdge(source="init_generic", target="worker_solution"),
                TaskEdge(source="worker_context", target="compose_generic"),
                TaskEdge(source="worker_solution", target="compose_generic"),
                TaskEdge(source="compose_generic", target="summarize"),
            ]
        else:
            retry_targets = [
                item.node_id
                for item in prior_rounds[-1].node_results
                if item.status in {"failed", "partial", "blocked"}
                and item.node_id != "summarize"
            ]
            retry_target = retry_targets[0] if retry_targets else "worker_solution"
            nodes = [
                TaskNode(
                    node_id=f"retry_{retry_target}",
                    title=f"Retry {retry_target}",
                    objective=f"Retry the {retry_target} phase, preserving concrete evidence and adapting the generic batch plan using prior failures.",
                    capability_bundles=[
                        "plan",
                        "task_manage",
                        "repo_fetch",
                        "docker_build_run",
                        "wdl_run",
                        "data_filter",
                        "operator_filter",
                        "metric_compute",
                        "web_search",
                        "web_fetch",
                        "db_access",
                        "api_call",
                        "validate",
                    ],
                    metadata={"retry_of": retry_target},
                ),
                TaskNode(
                    node_id="compose_generic",
                    title="Compose generic answer",
                    objective="Merge the retried generic worker outputs into one normal long-form user-facing answer.",
                    capability_bundles=["summarize", "validate"],
                ),
                TaskNode(
                    node_id="summarize",
                    title="Summarize generic outcome",
                    objective="Summarize the strongest verified generic outcome, worker contributions, blockers, and next-step recommendation.",
                    capability_bundles=["summarize"],
                ),
            ]
            edges = [
                TaskEdge(source=nodes[0].node_id, target="compose_generic"),
                TaskEdge(source="compose_generic", target="summarize"),
            ]
        return TaskGraph(
            graph_id=f"generic-r{round_index}",
            task_type="generic",
            round_index=round_index,
            nodes=_attach_common_node_metadata(
                nodes,
                task=task,
                task_type="generic",
                guidance_ids=guidance_ids,
            ),
            edges=edges,
            metadata=_graph_metadata(task=task, retrieved_cases=retrieved_cases, guidance_ids=guidance_ids),
        )

    def _plan_github2workspace(
        self,
        *,
        task: str,
        retrieved_cases: list[CaseTraceRecord],
        prior_rounds: list[TaskExecutionRound],
        round_index: int,
        guidance_ids: list[str],
    ) -> TaskGraph:
        if not prior_rounds:
            nodes = [
                TaskNode(
                    node_id="inspect",
                    title="Inspect repository",
                    objective="Inspect the repository, identify build/test assets, and record validation prerequisites.",
                    capability_bundles=["repo_fetch", "validate"],
                ),
                TaskNode(
                    node_id="build",
                    title="Build Docker image",
                    objective="Build or repair the Docker image and run a minimal container validation attempt.",
                    capability_bundles=["docker_build_run", "validate"],
                ),
                TaskNode(
                    node_id="wdl",
                    title="Run WDL workflow",
                    objective="Generate or repair WDL inputs and run Cromwell workflow validation.",
                    capability_bundles=["wdl_run", "validate"],
                ),
                TaskNode(
                    node_id="summarize",
                    title="Summarize workspace outcome",
                    objective="Summarize the strongest validated workspace state, blockers, and artifact paths.",
                    capability_bundles=["summarize"],
                ),
            ]
            edges = [
                TaskEdge(source="inspect", target="build"),
                TaskEdge(source="build", target="wdl"),
                TaskEdge(source="wdl", target="summarize"),
            ]
        else:
            first = _first_unresolved_node(prior_rounds[-1], fallback="build")
            if "inspect" in first:
                nodes = [
                    TaskNode(
                        node_id="retry_inspect",
                        title="Retry inspect",
                        objective="Retry repository inspection and correct the earlier repository understanding failure.",
                        capability_bundles=["repo_fetch", "validate"],
                    ),
                    TaskNode(
                        node_id="build",
                        title="Build Docker image",
                        objective="Build or repair the Docker image after refreshed inspection.",
                        capability_bundles=["docker_build_run", "validate"],
                    ),
                    TaskNode(
                        node_id="wdl",
                        title="Run WDL workflow",
                        objective="Retry WDL generation and validation after the repaired build path.",
                        capability_bundles=["wdl_run", "validate"],
                    ),
                    TaskNode(
                        node_id="summarize",
                        title="Summarize workspace outcome",
                        objective="Summarize the latest validated workspace state and remaining blockers.",
                        capability_bundles=["summarize"],
                    ),
                ]
                edges = [
                    TaskEdge(source="retry_inspect", target="build"),
                    TaskEdge(source="build", target="wdl"),
                    TaskEdge(source="wdl", target="summarize"),
                ]
            elif "wdl" in first:
                nodes = [
                    TaskNode(
                        node_id="retry_wdl",
                        title="Retry WDL workflow",
                        objective="Retry WDL generation and Cromwell validation using the latest validated build artifacts.",
                        capability_bundles=["wdl_run", "validate"],
                    ),
                    TaskNode(
                        node_id="summarize",
                        title="Summarize workspace outcome",
                        objective="Summarize the latest validated workspace state and remaining blockers.",
                        capability_bundles=["summarize"],
                    ),
                ]
                edges = [TaskEdge(source="retry_wdl", target="summarize")]
            else:
                nodes = [
                    TaskNode(
                        node_id="retry_build",
                        title="Retry build",
                        objective="Retry Docker build/validation and apply the smallest repair needed for the earlier build failure.",
                        capability_bundles=["docker_build_run", "validate"],
                    ),
                    TaskNode(
                        node_id="wdl",
                        title="Run WDL workflow",
                        objective="Retry WDL generation and Cromwell validation after the repaired build path.",
                        capability_bundles=["wdl_run", "validate"],
                    ),
                    TaskNode(
                        node_id="summarize",
                        title="Summarize workspace outcome",
                        objective="Summarize the latest validated workspace state and remaining blockers.",
                        capability_bundles=["summarize"],
                    ),
                ]
                edges = [
                    TaskEdge(source="retry_build", target="wdl"),
                    TaskEdge(source="wdl", target="summarize"),
                ]
        return TaskGraph(
            graph_id=f"github2workspace-r{round_index}",
            task_type="github2workspace",
            round_index=round_index,
            nodes=_attach_common_node_metadata(
                nodes,
                task=task,
                task_type="github2workspace",
                guidance_ids=guidance_ids,
            ),
            edges=edges,
            metadata=_graph_metadata(task=task, retrieved_cases=retrieved_cases, guidance_ids=guidance_ids),
        )

    def _plan_benchmark(
        self,
        *,
        task: str,
        retrieved_cases: list[CaseTraceRecord],
        prior_rounds: list[TaskExecutionRound],
        round_index: int,
        guidance_ids: list[str],
    ) -> TaskGraph:
        if not prior_rounds:
            nodes = [
                TaskNode(
                    node_id="register",
                    title="Register benchmark cases",
                    objective="Confirm benchmark inputs, register each tool/case pair, and verify staged constraints before execution.",
                    capability_bundles=["plan", "task_manage", "validate"],
                    metadata={"selected_tools": _select_benchmark_tools(task)},
                )
            ]
            edges: list[TaskEdge] = []
        elif _benchmark_register_round_finished(prior_rounds[-1]):
            tools = _benchmark_selected_tools_from_round(prior_rounds[-1])
            nodes = []
            edges = []
            for tool in tools:
                nodes.append(
                    TaskNode(
                        node_id=tool,
                        title=f"Run {tool}",
                        objective=f"Execute the staged benchmark workload for {tool} and record outputs, logs, and failure reasons.",
                        capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
                    )
                )
                edges.append(TaskEdge(source=tool, target="summarize"))
            nodes.append(
                TaskNode(
                    node_id="summarize",
                    title="Summarize benchmark outcomes",
                    objective="Aggregate tool results, metrics, blockers, and output paths into a benchmark summary.",
                    capability_bundles=["metric_compute", "summarize"],
                )
            )
        else:
            if _benchmark_register_needs_retry(prior_rounds[-1]):
                nodes = [
                    TaskNode(
                        node_id="retry_register",
                        title="Retry register",
                        objective="Inspect benchmark assets again, choose a compatible tool subset, and write a structured registration result for the next execution round.",
                        capability_bundles=["plan", "task_manage", "validate"],
                    ),
                    TaskNode(
                        node_id="summarize",
                        title="Summarize benchmark outcomes",
                        objective="Summarize retry outcomes, metrics, blockers, and output paths into a benchmark summary.",
                        capability_bundles=["metric_compute", "summarize"],
                    ),
                ]
                edges = [TaskEdge(source="retry_register", target="summarize")]
                return TaskGraph(
                    graph_id=f"benchmark-r{round_index}",
                    task_type="benchmark",
                    round_index=round_index,
                    nodes=_attach_common_node_metadata(
                        nodes,
                        task=task,
                        task_type="benchmark",
                        guidance_ids=guidance_ids,
                    ),
                    edges=edges,
                    metadata=_graph_metadata(task=task, retrieved_cases=retrieved_cases, guidance_ids=guidance_ids),
                )
            failed_tools = [
                item.node_id
                for item in prior_rounds[-1].node_results
                if item.status in {"failed", "partial"}
                and item.node_id not in {"register", "summarize"}
            ]
            if not failed_tools:
                failed_tools = [
                    item.node_id
                    for item in prior_rounds[-1].node_results
                    if item.status == "blocked"
                    and item.node_id not in {"register", "summarize"}
                ]
            nodes = [
                TaskNode(
                    node_id=f"retry_{tool}",
                    title=f"Retry {tool}",
                    objective=f"Retry the benchmark execution for {tool} and preserve structured failure reasons if it still cannot complete.",
                    capability_bundles=["docker_build_run", "wdl_run", "metric_compute"],
                    metadata={"tool": tool},
                )
                for tool in failed_tools
            ]
            nodes.append(
                TaskNode(
                    node_id="summarize",
                    title="Summarize benchmark outcomes",
                    objective="Aggregate retry outcomes, metrics, blockers, and output paths into a benchmark summary.",
                    capability_bundles=["metric_compute", "summarize"],
                )
            )
            edges = [
                TaskEdge(source=node.node_id, target="summarize")
                for node in nodes
                if node.node_id != "summarize"
            ]
        return TaskGraph(
            graph_id=f"benchmark-r{round_index}",
            task_type="benchmark",
            round_index=round_index,
            nodes=_attach_common_node_metadata(
                nodes,
                task=task,
                task_type="benchmark",
                guidance_ids=guidance_ids,
            ),
            edges=edges,
            metadata=_graph_metadata(task=task, retrieved_cases=retrieved_cases, guidance_ids=guidance_ids),
        )

    def _plan_report(
        self,
        *,
        task: str,
        retrieved_cases: list[CaseTraceRecord],
        prior_rounds: list[TaskExecutionRound],
        round_index: int,
        guidance_ids: list[str],
    ) -> TaskGraph:
        if not prior_rounds:
            nodes = [
                TaskNode(
                    node_id="init_report",
                    title="Initialize report run",
                    objective="Create the report run directory, save the request, outline evidence lanes, and define the report contract.",
                    capability_bundles=["plan", "task_manage", "validate"],
                ),
                TaskNode(
                    node_id="monitoring_lane",
                    title="Monitoring lane",
                    objective="Collect monitoring, operational, and official surveillance evidence relevant to the report topic.",
                    capability_bundles=["web_search", "web_fetch", "validate"],
                ),
                TaskNode(
                    node_id="local_data_lane",
                    title="Local data lane",
                    objective="Collect local structured data, registry, API, or database evidence relevant to the report topic.",
                    capability_bundles=["db_access", "api_call", "validate"],
                ),
                TaskNode(
                    node_id="literature_lane",
                    title="Literature and web lane",
                    objective="Collect literature, technical, and primary-source web evidence that complements the other lanes.",
                    capability_bundles=["web_search", "web_fetch", "api_call"],
                ),
                TaskNode(
                    node_id="compose_report",
                    title="Compose report",
                    objective="Compose the full report from the completed lanes and preserve evidence-backed uncertainty.",
                    capability_bundles=["summarize", "validate"],
                ),
                TaskNode(
                    node_id="summarize",
                    title="Summarize report outcome",
                    objective="Summarize report completion state, output paths, evidence layers, and remaining blockers.",
                    capability_bundles=["summarize"],
                ),
            ]
            edges = [
                TaskEdge(source="init_report", target="monitoring_lane"),
                TaskEdge(source="init_report", target="local_data_lane"),
                TaskEdge(source="init_report", target="literature_lane"),
                TaskEdge(source="monitoring_lane", target="compose_report"),
                TaskEdge(source="local_data_lane", target="compose_report"),
                TaskEdge(source="literature_lane", target="compose_report"),
                TaskEdge(source="compose_report", target="summarize"),
            ]
        else:
            failed_nodes = [
                item.node_id
                for item in prior_rounds[-1].node_results
                if item.status in {"failed", "partial"}
                and item.node_id != "summarize"
            ]
            if not failed_nodes:
                failed_nodes = [
                    item.node_id
                    for item in prior_rounds[-1].node_results
                    if item.status == "blocked"
                    and item.node_id != "summarize"
                ]
            retry_nodes = [
                TaskNode(
                    node_id=f"retry_{node_id}",
                    title=f"Retry {node_id}",
                    objective=f"Retry the {node_id} phase, preserving concrete evidence and blockers in report artifacts.",
                    capability_bundles=_report_retry_bundles(node_id),
                    metadata={"retry_of": node_id},
                )
                for node_id in failed_nodes
            ]
            nodes = [
                *retry_nodes,
                TaskNode(
                    node_id="compose_report",
                    title="Compose report",
                    objective="Compose the report from all available evidence lanes after retries complete.",
                    capability_bundles=["summarize", "validate"],
                ),
                TaskNode(
                    node_id="summarize",
                    title="Summarize report outcome",
                    objective="Summarize report completion state, output paths, evidence layers, and remaining blockers.",
                    capability_bundles=["summarize"],
                ),
            ]
            edges = [TaskEdge(source=node.node_id, target="compose_report") for node in retry_nodes]
            edges.append(TaskEdge(source="compose_report", target="summarize"))
        return TaskGraph(
            graph_id=f"report-r{round_index}",
            task_type="report",
            round_index=round_index,
            nodes=_attach_common_node_metadata(
                nodes,
                task=task,
                task_type="report",
                guidance_ids=guidance_ids,
            ),
            edges=edges,
            metadata=_graph_metadata(task=task, retrieved_cases=retrieved_cases, guidance_ids=guidance_ids),
        )


def _first_unresolved_node(round_result: TaskExecutionRound, *, fallback: str) -> str:
    failed_or_partial = [
        item.node_id for item in round_result.node_results if item.status in {"failed", "partial"}
    ]
    if failed_or_partial:
        return failed_or_partial[0]
    blocked = [item.node_id for item in round_result.node_results if item.status == "blocked"]
    if blocked:
        return blocked[0]
    return fallback


def _benchmark_register_round_finished(round_result: TaskExecutionRound) -> bool:
    if [node.node_id for node in round_result.graph.nodes] != ["register"]:
        return False
    if [item.node_id for item in round_result.node_results] != ["register"]:
        return False
    register = round_result.node_results[0]
    return register.status == "completed" and bool(_benchmark_selected_tools_from_result(register))


def _benchmark_register_needs_retry(round_result: TaskExecutionRound) -> bool:
    graph_node_ids = [node.node_id for node in round_result.graph.nodes]
    if graph_node_ids not in (["register"], ["retry_register"], ["register", "summarize"], ["retry_register", "summarize"]):
        return False
    node_ids = [item.node_id for item in round_result.node_results]
    if "register" not in node_ids and "retry_register" not in node_ids:
        return False
    register = next(
        (
            item
            for item in round_result.node_results
            if item.node_id in {"register", "retry_register"}
        ),
        None,
    )
    if register is None:
        return False
    if register.status == "completed" and _benchmark_selected_tools_from_result(register):
        return False
    return register.status in {"failed", "partial", "blocked"} or not _benchmark_selected_tools_from_result(register)


def _benchmark_selected_tools_from_round(round_result: TaskExecutionRound) -> list[str]:
    for item in round_result.node_results:
        if item.node_id not in {"register", "retry_register"}:
            continue
        tools = _benchmark_selected_tools_from_result(item)
        if tools:
            return tools
    return []


def _benchmark_selected_tools_from_result(result: WorkerNodeResult) -> list[str]:
    payload = result.spawned_subgraph
    if not isinstance(payload, dict):
        return []
    selected_tools = payload.get("selected_tools")
    if not isinstance(selected_tools, list):
        return []
    return [str(item) for item in selected_tools if isinstance(item, str) and item.strip()]


def _round_contains_only_analyze(round_result: TaskExecutionRound) -> bool:
    return [item.node_id for item in round_result.node_results] == ["init_generic"]


def _round_analyze_succeeded(round_result: TaskExecutionRound) -> bool:
    return any(
        item.node_id == "init_generic" and item.status == "completed"
        for item in round_result.node_results
    )


def _generic_execute_objective(approach: GenericApproach) -> str:
    if approach == "simple":
        return (
            "Execute the simplest useful version of the task: produce the smallest "
            "verified answer or artifact, avoid optional expansion, and preserve clear evidence."
        )
    if approach == "difficult":
        return (
            "Execute the most thorough version of the task: cover edge cases, broaden "
            "verification, and produce richer artifacts while staying within the original request."
        )
    return (
        "Execute the balanced version of the task: complete the main requested outcome "
        "with focused verification and avoid unnecessary expansion."
    )


def _extract_benchmark_tools(task: str) -> list[str]:
    catalog = _load_benchmark_catalog(task)
    if catalog is None:
        return []
    lowered = task.casefold()
    return [
        repo
        for repo in catalog.get("repo_cases", {})
        if str(repo).casefold() in lowered
    ]


def _select_benchmark_tools(task: str) -> list[str]:
    catalog = _load_benchmark_catalog(task)
    if catalog is None:
        return []
    explicit_tools = _extract_benchmark_tools(task)
    if explicit_tools:
        return explicit_tools

    dataset_key = _select_benchmark_dataset_key(task, catalog)
    if dataset_key:
        tools = _tools_for_dataset(catalog, dataset_key)
        if tools:
            return tools

    for key in catalog.get("datasets", {}):
        tools = _tools_for_dataset(catalog, str(key))
        if len(tools) >= 2:
            return tools
    for key in catalog.get("datasets", {}):
        tools = _tools_for_dataset(catalog, str(key))
        if tools:
            return tools
    return []


def _select_benchmark_dataset_key(task: str, catalog: dict[str, object]) -> str | None:
    lowered = task.casefold()
    datasets = catalog.get("datasets", {})
    if not isinstance(datasets, dict):
        return None
    for key in datasets:
        if str(key).casefold() in lowered:
            return str(key)
    for key, payload in datasets.items():
        if not isinstance(payload, dict):
            continue
        identifiers = [
            str(payload.get("dataset_id", "")),
            str(payload.get("description", "")),
        ]
        if any(identifier and identifier.casefold() in lowered for identifier in identifiers):
            return str(key)
    return None


def _tools_for_dataset(catalog: dict[str, object], dataset_key: str) -> list[str]:
    datasets = catalog.get("datasets", {})
    cases = catalog.get("repo_cases", {})
    if not isinstance(datasets, dict) or not isinstance(cases, dict):
        return []
    dataset = datasets.get(dataset_key)
    if isinstance(dataset, dict):
        shared_between = [
            str(item)
            for item in dataset.get("shared_between", [])
            if isinstance(item, str) and item in cases
        ]
        if shared_between:
            return shared_between
    return [
        str(repo)
        for repo, payload in cases.items()
        if isinstance(payload, dict) and payload.get("dataset_key") == dataset_key
    ]


def _load_benchmark_catalog(task: str) -> dict[str, object] | None:
    for path in _candidate_benchmark_catalog_paths(task):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("repo_cases"), dict):
            return payload
    return None


def _candidate_benchmark_catalog_paths(task: str) -> list[Path]:
    candidates: list[Path] = []
    for raw_path in _extract_task_paths(task):
        base = Path(raw_path)
        candidates.extend(
            [
                base / "datasets" / "benchmark_catalog.json",
                base / "benchmark_catalog.json",
            ]
        )

    seen: set[Path] = set()
    existing: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists():
            existing.append(candidate)
    return existing


def _report_retry_bundles(node_id: str) -> list[CapabilityBundle]:
    if "monitoring" in node_id:
        return ["web_search", "web_fetch", "validate"]
    if "local_data" in node_id:
        return ["db_access", "api_call", "validate"]
    if "literature" in node_id:
        return ["web_search", "web_fetch", "api_call"]
    if "compose" in node_id:
        return ["summarize", "validate"]
    return ["plan", "task_manage", "validate"]


def _graph_metadata(
    *,
    task: str,
    retrieved_cases: list[CaseTraceRecord],
    guidance_ids: list[str],
) -> dict[str, object]:
    return {
        "task": task,
        "task_paths": _extract_task_paths(task),
        "retrieved_cases": [item.to_dict() for item in retrieved_cases],
        "guidance_ids": list(guidance_ids),
        "guidance_summary": [
            guidance.summary
            for guidance in _TASK_GUIDANCE_REGISTRY
            if guidance.guidance_id in guidance_ids
        ],
    }


_ABS_PATH_RE = re.compile(r"(/[^ \n\t,;:]+)")


def _extract_task_paths(task: str) -> list[str]:
    """Extract absolute filesystem-like paths from the task text."""

    seen: list[str] = []
    for match in _ABS_PATH_RE.finditer(task):
        candidate = match.group(1).rstrip("。.,)")
        if candidate not in seen:
            seen.append(candidate)
    return seen


def _attach_common_node_metadata(
    nodes: list[TaskNode],
    *,
    task: str,
    task_type: TaskType,
    guidance_ids: list[str],
) -> list[TaskNode]:
    common = {
        "task": task,
        "task_type": task_type,
        "guidance_ids": list(guidance_ids),
    }
    updated: list[TaskNode] = []
    for node in nodes:
        updated.append(
            TaskNode(
                node_id=node.node_id,
                title=node.title,
                objective=node.objective,
                capability_bundles=list(node.capability_bundles),
                metadata={**common, **node.metadata},
            )
        )
    return updated


async def execute_graph_round(
    graph: TaskGraph,
    worker_runner,
) -> TaskExecutionRound:
    """Execute one graph round with dependency-aware parallel scheduling."""

    pending = {node.node_id: node for node in graph.nodes}
    by_target: dict[str, set[str]] = {}
    for edge in graph.edges:
        by_target.setdefault(edge.target, set()).add(edge.source)

    results: list[WorkerNodeResult] = []
    final_status: dict[str, WorkerStatus] = {}

    while pending:
        blocked_nodes = [
            node
            for node in pending.values()
            if any(final_status.get(dep) in {"failed", "blocked"} for dep in by_target.get(node.node_id, set()))
        ]
        if blocked_nodes:
            for node in blocked_nodes:
                results.append(
                    WorkerNodeResult(
                        node_id=node.node_id,
                        status="blocked",
                        summary="Blocked by failed dependency.",
                        failure_reason="blocked_by_failed_dependency",
                    )
                )
                final_status[node.node_id] = "blocked"
                pending.pop(node.node_id, None)
            continue

        ready = [
            node
            for node in pending.values()
            if all(final_status.get(dep) == "completed" for dep in by_target.get(node.node_id, set()))
        ]
        if not ready:
            for node in list(pending.values()):
                results.append(
                    WorkerNodeResult(
                        node_id=node.node_id,
                        status="blocked",
                        summary="Blocked by unresolved dependency chain.",
                        failure_reason="blocked_by_unresolved_dependency",
                    )
                )
                final_status[node.node_id] = "blocked"
                pending.pop(node.node_id, None)
            break

        batch_results = await asyncio.gather(*(_run_worker(node, worker_runner) for node in ready))
        for node, result in zip(ready, batch_results, strict=True):
            results.append(
                WorkerNodeResult(
                    node_id=node.node_id,
                    status=result.status,
                    summary=result.summary,
                    artifacts=list(result.artifacts),
                    evidence=list(result.evidence),
                    next_action_hint=result.next_action_hint,
                    failure_reason=result.failure_reason,
                    spawned_subgraph=result.spawned_subgraph,
                )
            )
            final_status[node.node_id] = result.status
            pending.pop(node.node_id, None)

    return TaskExecutionRound(graph=graph, node_results=results)


async def _run_worker(node: TaskNode, worker_runner) -> WorkerResult:
    try:
        result = await worker_runner(node)
    except GraphBubbleUp:
        raise
    except Exception as exc:  # pragma: no cover - defensive conversion
        return WorkerResult(
            status="failed",
            summary=f"{node.node_id} failed with an unexpected exception.",
            failure_reason=f"{type(exc).__name__}: {exc}",
        )
    return result


def decide_supervisor_step(
    round_result: TaskExecutionRound,
    *,
    max_rounds: int = 2,
) -> SupervisorDecision:
    if (
        round_result.failed_count == 0
        and round_result.blocked_count == 0
        and round_result.partial_count == 0
    ):
        return SupervisorDecision(decision="stop", reason="All nodes completed.")
    if round_result.graph.round_index >= max_rounds:
        failed_nodes = [
            item.node_id
            for item in round_result.node_results
            if item.status in {"failed", "blocked", "partial"}
        ]
        return SupervisorDecision(
            decision="stop",
            reason="Reached max rounds with unresolved nodes.",
            failed_nodes=failed_nodes,
        )
    failed_nodes = [
        item.node_id
        for item in round_result.node_results
        if item.status in {"failed", "blocked", "partial"}
    ]
    return SupervisorDecision(
        decision="replan",
        reason="Replan to retry unresolved nodes.",
        failed_nodes=failed_nodes,
    )
