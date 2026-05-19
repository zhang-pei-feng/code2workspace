"""Generic orchestration experience records and distilled skill material."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "then",
    "have",
    "what",
    "which",
    "when",
    "where",
    "will",
    "would",
    "should",
    "could",
    "please",
    "just",
    "only",
    "give",
    "show",
    "tell",
    "说明",
    "解释",
    "请",
    "一下",
    "现在",
    "什么",
    "怎么",
    "以及",
    "并且",
    "保持",
    "回答",
    "简短",
    "尽量",
    "基于",
    "本地",
    "代码",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def experience_skill_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".code2workspace" / "skills" / "orchestration" / "generic-experience"


def records_dir(root: Path | None = None) -> Path:
    return experience_skill_root(root) / "records"


def generated_guidance_path(root: Path | None = None) -> Path:
    return experience_skill_root(root) / "generated" / "generic_orchestration_experience.md"


@dataclass(slots=True)
class ProblemClassification:
    task_family: str
    intent: str
    evidence_mode: str
    complexity: str
    scope: str


@dataclass(slots=True)
class ProblemAbstraction:
    summary: str
    constraints: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProblemInstance:
    prompt_excerpt: str
    abstracted_instance: str


@dataclass(slots=True)
class Trajectory:
    graph_shape: str
    node_ids: list[str] = field(default_factory=list)
    round_count: int = 0
    node_count: int = 0
    tool_rhythm: str = ""
    stop_rule: str = ""
    answer_style: str = ""
    evidence_pattern: str = ""


@dataclass(slots=True)
class TrajectoryEffect:
    acceptance: str
    case_score: float
    split_mean_score: float
    traceability_score: float
    evidence_score: float
    efficiency_score: float
    completion_level: str
    completion_status: str
    source_url_count: int
    findings: list[str] = field(default_factory=list)
    score_delta_vs_previous: float = 0.0


@dataclass(slots=True)
class Applicability:
    use_when: str
    avoid_when: str


@dataclass(slots=True)
class GenericOrchestrationExperienceRecord:
    record_id: str
    created_at: str
    source: dict[str, Any]
    problem_classification: ProblemClassification
    problem_abstraction: ProblemAbstraction
    problem_instance: ProblemInstance
    trajectory: Trajectory
    trajectory_explain: str
    trajectory_effect: TrajectoryEffect
    applicability: Applicability
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = round(float(self.confidence), 3)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GenericOrchestrationExperienceRecord":
        return cls(
            record_id=str(payload["record_id"]),
            created_at=str(payload["created_at"]),
            source=dict(payload.get("source") or {}),
            problem_classification=ProblemClassification(**dict(payload["problem_classification"])),
            problem_abstraction=ProblemAbstraction(**dict(payload["problem_abstraction"])),
            problem_instance=ProblemInstance(**dict(payload["problem_instance"])),
            trajectory=Trajectory(**dict(payload["trajectory"])),
            trajectory_explain=str(payload["trajectory_explain"]),
            trajectory_effect=TrajectoryEffect(**dict(payload["trajectory_effect"])),
            applicability=Applicability(**dict(payload["applicability"])),
            confidence=float(payload.get("confidence", 0.0)),
        )


def load_records(*, root: Path | None = None) -> list[GenericOrchestrationExperienceRecord]:
    base = records_dir(root)
    if not base.exists():
        return []
    records: list[GenericOrchestrationExperienceRecord] = []
    for path in sorted(base.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(GenericOrchestrationExperienceRecord.from_dict(payload))
    return records


def write_record(record: GenericOrchestrationExperienceRecord, *, root: Path | None = None) -> Path:
    path = records_dir(root) / f"{record.record_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def rebuild_distilled_guidance(*, root: Path | None = None) -> Path:
    records = sorted(
        load_records(root=root),
        key=lambda item: (
            item.confidence,
            item.trajectory_effect.case_score,
            item.trajectory_effect.score_delta_vs_previous,
        ),
        reverse=True,
    )
    path = generated_guidance_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Generic Orchestration Experience",
        "",
        "- Use these distilled experience patterns as planning hints, not as hard-coded answers.",
        "- Match graph size to the task; prefer the smallest graph that still protects evidence quality and answer usefulness.",
        "- Reuse a recorded trajectory only when its applicability and constraints match the current task.",
        "",
    ]
    for record in records[:6]:
        effect = record.trajectory_effect
        trajectory = record.trajectory
        abstraction = record.problem_abstraction
        lines.extend(
            [
                f"## {record.record_id}",
                "",
                f"- Applies to: {abstraction.summary}",
                f"- Preferred trajectory: {trajectory.graph_shape}; nodes={', '.join(trajectory.node_ids[:6]) or 'n/a'}; stop rule={trajectory.stop_rule}",
                f"- Why it worked: {record.trajectory_explain}",
                f"- Use when: {record.applicability.use_when}",
                f"- Avoid when: {record.applicability.avoid_when}",
                f"- Observed effect: case_score={effect.case_score:.1f}, delta_vs_previous={effect.score_delta_vs_previous:+.1f}, evidence_score={effect.evidence_score:.1f}, efficiency_score={effect.efficiency_score:.1f}, traceability_score={effect.traceability_score:.1f}",
                "",
            ]
        )
    if len(lines) <= 6:
        lines.extend(
            [
                "## Empty",
                "",
                "- No accepted generic experience records yet. Fall back to the stable generic family guidance.",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def retrieve_experience_guidance_lines(
    *,
    task: str,
    limit: int = 3,
    root: Path | None = None,
) -> list[str]:
    if not task.strip():
        return []
    ranked = sorted(
        (
            (score_record_for_task(record, task), record)
            for record in load_records(root=root)
        ),
        key=lambda item: (item[0], item[1].confidence, item[1].trajectory_effect.case_score),
        reverse=True,
    )
    lines: list[str] = []
    for score, record in ranked[:limit]:
        if score <= 0:
            continue
        lines.extend(
            [
                f"Retrieved generic experience ({record.record_id}): applies when {record.applicability.use_when}",
                f"Preferred trajectory from experience: {record.trajectory.graph_shape}; nodes={', '.join(record.trajectory.node_ids[:5]) or 'n/a'}; tool rhythm={record.trajectory.tool_rhythm or 'keep tool use bounded'}",
                f"Experience rationale: {record.trajectory_explain}",
            ]
        )
    return lines


def score_record_for_task(record: GenericOrchestrationExperienceRecord, task: str) -> float:
    tokens = set(_keywords(task))
    if not tokens:
        return 0.0
    record_tokens = set(
        _keywords(
            " ".join(
                [
                    record.problem_classification.intent,
                    record.problem_classification.evidence_mode,
                    record.problem_classification.scope,
                    record.problem_abstraction.summary,
                    " ".join(record.problem_abstraction.constraints),
                    " ".join(record.problem_abstraction.tags),
                    record.problem_instance.abstracted_instance,
                    record.applicability.use_when,
                ]
            )
        )
    )
    overlap = len(tokens & record_tokens)
    score = overlap * 10.0
    if _mentions_local_only(task) and "local_only" == record.problem_classification.evidence_mode:
        score += 8.0
    if _mentions_short_answer(task) and "short_answer" in record.problem_abstraction.constraints:
        score += 5.0
    if _mentions_evidence_boundary(task) and "evidence_boundary" in record.problem_abstraction.constraints:
        score += 6.0
    if _mentions_computation(task) and "computed_local" == record.problem_classification.evidence_mode:
        score += 8.0
    return score + record.confidence


def build_experience_record(
    *,
    case_id: str,
    prompt: str,
    split: str,
    variant: str,
    harness_run_root: Path,
    orchestration_run_dir: Path,
    generic_trace_summary: dict[str, Any],
    baseline_split_mean_score: float,
    candidate_split_mean_score: float,
    created_at: str | None = None,
) -> GenericOrchestrationExperienceRecord:
    created = created_at or datetime.now(tz=UTC).isoformat(timespec="seconds")
    metrics = dict(generic_trace_summary.get("metrics") or {})
    scores = {
        str(name): float(value)
        for name, value in dict(generic_trace_summary.get("scores") or {}).items()
        if isinstance(value, int | float)
    }
    findings = [
        str(item)
        for item in generic_trace_summary.get("findings", [])
        if isinstance(item, str)
    ]
    node_ids = _latest_graph_node_ids(orchestration_run_dir)
    classification = ProblemClassification(
        task_family="generic",
        intent=_infer_intent(prompt),
        evidence_mode=_infer_evidence_mode(prompt, metrics),
        complexity=_infer_complexity(metrics),
        scope=_infer_scope(prompt),
    )
    abstraction = ProblemAbstraction(
        summary=_abstract_problem(prompt, classification),
        constraints=_problem_constraints(prompt),
        tags=_problem_tags(prompt, classification),
    )
    trajectory = Trajectory(
        graph_shape=str(metrics.get("graph_shape_label", "unknown")),
        node_ids=node_ids,
        round_count=int(metrics.get("round_count", 0) or 0),
        node_count=int(metrics.get("node_count", 0) or 0),
        tool_rhythm=_tool_rhythm(metrics),
        stop_rule=_stop_rule(metrics),
        answer_style=_answer_style(prompt),
        evidence_pattern=_evidence_pattern(metrics),
    )
    effect = TrajectoryEffect(
        acceptance="accepted",
        case_score=float(_round_score_from_summary(scores)),
        split_mean_score=round(candidate_split_mean_score, 3),
        traceability_score=float(scores.get("traceability_score", 0.0)),
        evidence_score=float(scores.get("evidence_score", 0.0)),
        efficiency_score=float(scores.get("efficiency_score", 0.0)),
        completion_level=str(generic_trace_summary.get("completion_level", "")),
        completion_status=str(generic_trace_summary.get("completion_status", "")),
        source_url_count=int(metrics.get("source_url_count", 0) or 0),
        findings=findings[:8],
        score_delta_vs_previous=round(candidate_split_mean_score - baseline_split_mean_score, 3),
    )
    record = GenericOrchestrationExperienceRecord(
        record_id=_record_id(case_id=case_id, variant=variant, run_dir=orchestration_run_dir),
        created_at=created,
        source={
            "case_id": case_id,
            "split": split,
            "variant": variant,
            "harness_run_root": str(harness_run_root),
            "orchestration_run_dir": str(orchestration_run_dir),
        },
        problem_classification=classification,
        problem_abstraction=abstraction,
        problem_instance=ProblemInstance(
            prompt_excerpt=_truncate(prompt, 180),
            abstracted_instance=_abstract_instance(prompt, abstraction.summary),
        ),
        trajectory=trajectory,
        trajectory_explain=_trajectory_explain(classification, trajectory, effect),
        trajectory_effect=effect,
        applicability=Applicability(
            use_when=_use_when(classification, abstraction, trajectory),
            avoid_when=_avoid_when(classification, abstraction),
        ),
        confidence=_confidence(effect=effect, trajectory=trajectory),
    )
    return record


def _record_id(*, case_id: str, variant: str, run_dir: Path) -> str:
    digest = hashlib.sha1(str(run_dir).encode("utf-8")).hexdigest()[:10]
    return f"{case_id}__{variant}__{digest}"


def _round_score_from_summary(scores: dict[str, float]) -> float:
    if not scores:
        return 0.0
    return round(sum(scores.values()) / len(scores), 3)


def _keywords(text: str) -> list[str]:
    return [
        token.casefold()
        for token in _WORD_RE.findall(text)
        if len(token) > 1 and token.casefold() not in _STOPWORDS
    ]


def _mentions_local_only(text: str) -> bool:
    lowered = text.casefold()
    return "本地代码" in text or "只基于本地" in text or "local" in lowered


def _mentions_short_answer(text: str) -> bool:
    return any(marker in text for marker in ("简短", "口语化", "简洁", "短答", "一句话"))


def _mentions_evidence_boundary(text: str) -> bool:
    return "证据边界" in text or "区分证据" in text or "evidence" in text.casefold()


def _mentions_computation(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in ("预测", "计算", "算子", "metric", "compute", "operator"))


def _infer_intent(prompt: str) -> str:
    lowered = prompt.casefold()
    if _mentions_computation(prompt):
        return "computed_judgment"
    if any(
        marker in prompt
        for marker in ("为什么", "怎么来的", "差别", "记录哪些", "记录什么", "记录到什么细粒度", "score")
    ):
        return "local_code_explanation"
    if any(marker in prompt for marker in ("判断", "研判", "是否", "能不能")):
        return "evidence_judgment"
    if any(marker in lowered for marker in ("fix", "patch", "repair")):
        return "repo_repair"
    return "generic_analysis"


def _infer_evidence_mode(prompt: str, metrics: dict[str, Any]) -> str:
    if _mentions_computation(prompt):
        return "computed_local"
    if _mentions_local_only(prompt):
        return "local_only"
    if int(metrics.get("source_url_count", 0) or 0) > 0:
        return "trusted_web"
    return "mixed_or_unspecified"


def _infer_complexity(metrics: dict[str, Any]) -> str:
    node_count = int(metrics.get("node_count", 0) or 0)
    if node_count <= 3:
        return "small"
    if node_count <= 5:
        return "medium"
    return "large"


def _infer_scope(prompt: str) -> str:
    if _mentions_local_only(prompt):
        return "repo_local"
    if "仓库" in prompt or "repo" in prompt.casefold():
        return "repository"
    return "generic"


def _problem_constraints(prompt: str) -> list[str]:
    constraints: list[str] = []
    if _mentions_local_only(prompt):
        constraints.append("local_only")
    if _mentions_short_answer(prompt):
        constraints.append("short_answer")
    if _mentions_evidence_boundary(prompt):
        constraints.append("evidence_boundary")
    if "不要正式" in prompt or "口头" in prompt:
        constraints.append("non_formal_answer")
    if _mentions_computation(prompt):
        constraints.append("may_need_computation")
    return constraints


def _problem_tags(prompt: str, classification: ProblemClassification) -> list[str]:
    tags = [classification.intent, classification.evidence_mode, classification.scope]
    tags.extend(_keywords(prompt)[:10])
    deduped: list[str] = []
    for tag in tags:
        if tag and tag not in deduped:
            deduped.append(tag)
    return deduped


def _abstract_problem(prompt: str, classification: ProblemClassification) -> str:
    if classification.intent == "local_code_explanation":
        return "Explain repo-local runtime or artifact behavior from local code and keep the answer compact."
    if classification.intent == "evidence_judgment":
        return "Give a bounded judgment with explicit evidence boundaries and no unnecessary report structure."
    if classification.intent == "computed_judgment":
        return "Produce a judgment that may require local operator-backed computation before synthesis."
    if classification.intent == "repo_repair":
        return "Inspect local code, repair the concrete issue, then summarize the fix path."
    return "Handle a generic task with the smallest graph that still preserves evidence and answer quality."


def _abstract_instance(prompt: str, abstraction: str) -> str:
    return f"{abstraction} Example prompt shape: {_truncate(prompt, 120)}"


def _tool_rhythm(metrics: dict[str, Any]) -> str:
    total = int(metrics.get("tool_event_count", 0) or 0)
    if total <= 15:
        return "very_light"
    if total <= 40:
        return "bounded"
    if total <= 80:
        return "moderate"
    return "heavy"


def _stop_rule(metrics: dict[str, Any]) -> str:
    if int(metrics.get("source_url_count", 0) or 0) == 0:
        return "stop after enough local artifacts are read for synthesis"
    return "stop after enough source-backed evidence exists for one bounded synthesis pass"


def _answer_style(prompt: str) -> str:
    if _mentions_short_answer(prompt):
        return "short_direct_answer"
    if "口语" in prompt or "口头" in prompt:
        return "oral_or_conversational"
    return "normal_explanatory_answer"


def _evidence_pattern(metrics: dict[str, Any]) -> str:
    if bool(metrics.get("has_evidence_boundary")):
        return "explicit_evidence_boundary"
    if int(metrics.get("source_url_count", 0) or 0) > 0:
        return "source_backed_without_explicit_boundary"
    return "local_artifact_backed"


def _trajectory_explain(
    classification: ProblemClassification,
    trajectory: Trajectory,
    effect: TrajectoryEffect,
) -> str:
    reason = (
        "This trajectory kept the graph small enough for the task while still leaving a clear synthesis step."
        if trajectory.node_count <= 4
        else "This trajectory used multiple nodes because the task needed distinct evidence or execution lanes."
    )
    if classification.evidence_mode == "local_only":
        reason += " It fits local-only questions because it can stop after the needed repo artifacts are read."
    if classification.evidence_mode == "computed_local":
        reason += " It keeps computation explicit instead of hiding operator execution inside synthesis."
    if effect.evidence_score >= 80:
        reason += " The resulting answer kept evidence provenance visible."
    return reason


def _use_when(
    classification: ProblemClassification,
    abstraction: ProblemAbstraction,
    trajectory: Trajectory,
) -> str:
    if classification.evidence_mode == "local_only":
        return "the user wants a repo-local explanation or decision and one bounded evidence lane is enough"
    if classification.evidence_mode == "computed_local":
        return "the task may require local operator-backed computation before answering"
    if trajectory.graph_shape == "direct_or_minimal":
        return "the task is narrow and does not justify multiple parallel workers"
    return abstraction.summary.casefold()


def _avoid_when(
    classification: ProblemClassification,
    abstraction: ProblemAbstraction,
) -> str:
    if classification.evidence_mode == "local_only":
        return "the task explicitly needs broad web discovery, monitoring, or a formal report artifact"
    if "short_answer" in abstraction.constraints:
        return "the task has already grown into a multi-lane investigation with unresolved blockers"
    return "the task needs a wider formal report structure or a different family-specific graph"


def _confidence(*, effect: TrajectoryEffect, trajectory: Trajectory) -> float:
    score = 40.0
    score += min(effect.traceability_score, 100.0) * 0.2
    score += min(effect.evidence_score, 100.0) * 0.15
    score += min(effect.efficiency_score, 100.0) * 0.15
    if effect.score_delta_vs_previous > 0:
        score += min(effect.score_delta_vs_previous * 2.0, 10.0)
    if trajectory.graph_shape in {"direct_or_minimal", "evidence_then_synthesis", "inspect_fix_verify"}:
        score += 5.0
    return round(min(score, 100.0), 3)


def _latest_graph_node_ids(run_dir: Path) -> list[str]:
    graph_files = sorted(run_dir.glob("graph_round_*.json"))
    if not graph_files:
        return []
    try:
        payload = json.loads(graph_files[-1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    graph = payload.get("graph") if isinstance(payload, dict) else None
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, list):
        return []
    return [
        str(item.get("node_id"))
        for item in nodes
        if isinstance(item, dict) and item.get("node_id")
    ]


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"
