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
_TABLE_SCHEMA_VERSION = 1
_MAJOR_UPDATE_INTERVAL = 20


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def experience_skill_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / ".code2workspace" / "skills" / "orchestration" / "generic-experience"


def records_dir(root: Path | None = None) -> Path:
    return experience_skill_root(root) / "records"


def generated_guidance_path(root: Path | None = None) -> Path:
    return experience_skill_root(root) / "generated" / "generic_orchestration_experience.md"


def experience_table_path(root: Path | None = None) -> Path:
    return experience_skill_root(root) / "experience_table.json"


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


@dataclass(slots=True)
class ExperienceTableEntry:
    entry_id: str
    classification: str
    problem_abstraction: str
    explain: str
    instance_paths: list[str] = field(default_factory=list)
    instance_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "classification": self.classification,
            "problem_abstraction": self.problem_abstraction,
            "explain": self.explain,
            "instance_paths": list(self.instance_paths),
            "instance_count": int(self.instance_count),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExperienceTableEntry":
        return cls(
            entry_id=str(payload.get("entry_id") or ""),
            classification=str(payload.get("classification") or ""),
            problem_abstraction=str(payload.get("problem_abstraction") or ""),
            explain=str(payload.get("explain") or ""),
            instance_paths=[
                str(path)
                for path in payload.get("instance_paths", [])
                if isinstance(path, str) and path.strip()
            ],
            instance_count=int(payload.get("instance_count", 0) or 0),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


@dataclass(slots=True)
class ExperienceTable:
    schema_version: int = _TABLE_SCHEMA_VERSION
    total_instance_count: int = 0
    pending_major_update_count: int = 0
    last_major_update_at: str | None = None
    entries: list[ExperienceTableEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "total_instance_count": int(self.total_instance_count),
            "pending_major_update_count": int(self.pending_major_update_count),
            "last_major_update_at": self.last_major_update_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExperienceTable":
        return cls(
            schema_version=int(payload.get("schema_version", _TABLE_SCHEMA_VERSION) or _TABLE_SCHEMA_VERSION),
            total_instance_count=int(payload.get("total_instance_count", 0) or 0),
            pending_major_update_count=int(payload.get("pending_major_update_count", 0) or 0),
            last_major_update_at=(
                str(payload.get("last_major_update_at"))
                if payload.get("last_major_update_at")
                else None
            ),
            entries=[
                ExperienceTableEntry.from_dict(entry)
                for entry in payload.get("entries", [])
                if isinstance(entry, dict)
            ],
        )


def load_records(*, root: Path | None = None) -> list[GenericOrchestrationExperienceRecord]:
    return [record for _, record in _load_record_items(root=root)]


def write_record(record: GenericOrchestrationExperienceRecord, *, root: Path | None = None) -> Path:
    path = records_dir(root) / f"{record.record_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    table_existed = experience_table_path(root).exists()
    path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _append_record_to_experience_table(
        record,
        record_path=path,
        root=root,
        include_existing_records=not table_existed,
    )
    return path


def load_experience_table(*, root: Path | None = None) -> ExperienceTable | None:
    path = experience_table_path(root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    table = ExperienceTable.from_dict(payload)
    _normalize_experience_table(table, reset_pending=False, major_update_at=None)
    return table


def rebuild_experience_table(*, root: Path | None = None) -> Path:
    table = _build_table_from_record_items(
        _load_record_items(root=root),
        root=root,
        pending_count=0,
        last_major_update_at=_now_iso(),
    )
    _normalize_experience_table(table, reset_pending=True, major_update_at=table.last_major_update_at)
    path = experience_table_path(root)
    _write_experience_table(table, path=path)
    return path


def maybe_rebuild_experience_table(*, root: Path | None = None, force: bool = False) -> Path | None:
    table = load_experience_table(root=root)
    if table is None:
        return rebuild_experience_table(root=root)
    if not force and table.pending_major_update_count < _MAJOR_UPDATE_INTERVAL:
        return None
    major_update_at = _now_iso()
    _normalize_experience_table(table, reset_pending=True, major_update_at=major_update_at)
    path = experience_table_path(root)
    _write_experience_table(table, path=path)
    return path


def rebuild_distilled_guidance(*, root: Path | None = None) -> Path:
    table = _table_for_read(root=root)
    entries = sorted(
        table.entries,
        key=lambda item: (item.instance_count, item.updated_at, item.entry_id),
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
    for entry in entries[:8]:
        example_paths = ", ".join(entry.instance_paths[:3]) or "n/a"
        lines.extend(
            [
                f"## {entry.entry_id}",
                "",
                f"- Classification: {entry.classification}",
                f"- Problem abstraction: {entry.problem_abstraction}",
                f"- Explain: {entry.explain}",
                f"- Instance count: {entry.instance_count}",
                f"- Example instance paths: {example_paths}",
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
    table = _table_for_read(root=root)
    ranked = sorted(
        (
            (score_table_entry_for_task(entry, task), entry)
            for entry in table.entries
        ),
        key=lambda item: (item[0], item[1].instance_count, item[1].updated_at),
        reverse=True,
    )
    lines: list[str] = []
    record_cache = _record_cache_by_instance_path(root=root)
    for score, entry in ranked[:limit]:
        if score <= 0:
            continue
        instance_path, record = _representative_instance(entry, record_cache)
        if record is None:
            lines.extend(
                [
                    f"Retrieved generic experience ({entry.entry_id}): classification={entry.classification}; instances={entry.instance_count}; example={instance_path or 'n/a'}",
                    f"Experience abstraction: {entry.problem_abstraction}",
                    f"Experience rationale: {entry.explain}",
                ]
            )
            continue
        lines.extend(
            [
                f"Retrieved generic experience ({entry.entry_id}): classification={entry.classification}; applies when {record.applicability.use_when}; example={instance_path or record.record_id}",
                f"Preferred trajectory from experience: {record.trajectory.graph_shape}; nodes={', '.join(record.trajectory.node_ids[:5]) or 'n/a'}; tool rhythm={record.trajectory.tool_rhythm or 'keep tool use bounded'}",
                f"Experience abstraction: {entry.problem_abstraction}",
                f"Experience rationale: {entry.explain}",
            ]
        )
    return lines


def score_table_entry_for_task(entry: ExperienceTableEntry, task: str) -> float:
    tokens = set(_keywords(task))
    if not tokens:
        return 0.0
    entry_tokens = set(
        _keywords(
            " ".join(
                [
                    entry.classification.replace("__", " "),
                    entry.problem_abstraction,
                    entry.explain,
                ]
            )
        )
    )
    overlap = len(tokens & entry_tokens)
    score = overlap * 10.0
    if _mentions_local_only(task) and "local_only" in entry.classification:
        score += 8.0
    if _mentions_computation(task) and "computed_local" in entry.classification:
        score += 8.0
    if _mentions_evidence_boundary(task) and "evidence" in entry.explain.casefold():
        score += 4.0
    return score + min(entry.instance_count, 5) * 0.25


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


def _load_record_items(
    *,
    root: Path | None = None,
) -> list[tuple[Path, GenericOrchestrationExperienceRecord]]:
    base = records_dir(root)
    if not base.exists():
        return []
    items: list[tuple[Path, GenericOrchestrationExperienceRecord]] = []
    for path in sorted(base.glob("*.json")):
        record = _load_record_file(path)
        if record is not None:
            items.append((path, record))
    return items


def _load_record_file(path: Path) -> GenericOrchestrationExperienceRecord | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return GenericOrchestrationExperienceRecord.from_dict(payload)


def _build_table_from_record_items(
    items: list[tuple[Path, GenericOrchestrationExperienceRecord]],
    *,
    root: Path | None,
    pending_count: int,
    last_major_update_at: str | None,
) -> ExperienceTable:
    table = ExperienceTable(
        schema_version=_TABLE_SCHEMA_VERSION,
        pending_major_update_count=pending_count,
        last_major_update_at=last_major_update_at,
    )
    for path, record in items:
        _append_record_to_table(
            table,
            record=record,
            record_path=path,
            root=root,
            timestamp=record.created_at or _now_iso(),
            count_as_pending=False,
        )
    _refresh_table_entry_explains_from_records(table, items=items, root=root)
    _normalize_experience_table(table, reset_pending=False, major_update_at=last_major_update_at)
    table.pending_major_update_count = pending_count
    return table


def _append_record_to_experience_table(
    record: GenericOrchestrationExperienceRecord,
    *,
    record_path: Path,
    root: Path | None,
    include_existing_records: bool,
) -> None:
    if include_existing_records:
        table = _build_table_from_record_items(
            [
                (path, existing_record)
                for path, existing_record in _load_record_items(root=root)
                if path.resolve() != record_path.resolve()
            ],
            root=root,
            pending_count=0,
            last_major_update_at=None,
        )
    else:
        table = load_experience_table(root=root) or ExperienceTable()
    _append_record_to_table(
        table,
        record=record,
        record_path=record_path,
        root=root,
        timestamp=_now_iso(),
        count_as_pending=True,
    )
    path = experience_table_path(root)
    _write_experience_table(table, path=path)
    maybe_rebuild_experience_table(root=root)


def _append_record_to_table(
    table: ExperienceTable,
    *,
    record: GenericOrchestrationExperienceRecord,
    record_path: Path,
    root: Path | None,
    timestamp: str,
    count_as_pending: bool,
) -> None:
    classification = _classification_key(record)
    abstraction = record.problem_abstraction.summary
    instance_path = _instance_path(record_path, root=root)
    entry = _matching_table_entry(table, classification=classification, abstraction=abstraction)
    if entry is None:
        entry = ExperienceTableEntry(
            entry_id=_entry_id(classification=classification, abstraction=abstraction),
            classification=classification,
            problem_abstraction=abstraction,
            explain=_strategy_explain_for_records([record]),
            instance_paths=[],
            instance_count=0,
            created_at=record.created_at or timestamp,
            updated_at=timestamp,
        )
        table.entries.append(entry)
    if instance_path not in entry.instance_paths:
        entry.instance_paths.append(instance_path)
        entry.instance_count = len(entry.instance_paths)
        table.total_instance_count += 1
        if count_as_pending:
            table.pending_major_update_count += 1
    entry.updated_at = timestamp


def _matching_table_entry(
    table: ExperienceTable,
    *,
    classification: str,
    abstraction: str,
) -> ExperienceTableEntry | None:
    for entry in table.entries:
        if entry.classification == classification:
            return entry
    for entry in table.entries:
        if entry.problem_abstraction == abstraction:
            return entry
    return None


def _refresh_table_entry_explains_from_records(
    table: ExperienceTable,
    *,
    items: list[tuple[Path, GenericOrchestrationExperienceRecord]],
    root: Path | None,
) -> None:
    records_by_path = {
        _instance_path(path, root=root): record
        for path, record in items
    }
    for entry in table.entries:
        records = [
            records_by_path[path]
            for path in entry.instance_paths
            if path in records_by_path
        ]
        if records:
            entry.explain = _strategy_explain_for_records(records)


def _normalize_experience_table(
    table: ExperienceTable,
    *,
    reset_pending: bool,
    major_update_at: str | None,
) -> None:
    normalized_entries: list[ExperienceTableEntry] = []
    for entry in table.entries:
        paths = sorted({path for path in entry.instance_paths if path.strip()})
        if not paths:
            continue
        entry.instance_paths = paths
        entry.instance_count = len(paths)
        if not entry.entry_id:
            entry.entry_id = _entry_id(
                classification=entry.classification,
                abstraction=entry.problem_abstraction,
            )
        if not entry.created_at:
            entry.created_at = major_update_at or _now_iso()
        if not entry.updated_at:
            entry.updated_at = entry.created_at
        normalized_entries.append(entry)
    normalized_entries.sort(key=lambda item: (item.classification, item.problem_abstraction, item.entry_id))
    table.schema_version = _TABLE_SCHEMA_VERSION
    table.entries = normalized_entries
    table.total_instance_count = sum(entry.instance_count for entry in normalized_entries)
    if reset_pending:
        table.pending_major_update_count = 0
        table.last_major_update_at = major_update_at or _now_iso()


def _write_experience_table(table: ExperienceTable, *, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(table.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _table_for_read(*, root: Path | None = None) -> ExperienceTable:
    table = load_experience_table(root=root)
    if table is not None:
        return table
    return _build_table_from_record_items(
        _load_record_items(root=root),
        root=root,
        pending_count=0,
        last_major_update_at=None,
    )


def _record_cache_by_instance_path(
    *,
    root: Path | None,
) -> dict[str, GenericOrchestrationExperienceRecord]:
    cache: dict[str, GenericOrchestrationExperienceRecord] = {}
    for path, record in _load_record_items(root=root):
        cache[_instance_path(path, root=root)] = record
    return cache


def _representative_instance(
    entry: ExperienceTableEntry,
    record_cache: dict[str, GenericOrchestrationExperienceRecord],
) -> tuple[str | None, GenericOrchestrationExperienceRecord | None]:
    best_path: str | None = None
    best_record: GenericOrchestrationExperienceRecord | None = None
    best_score: tuple[float, float, str] | None = None
    for instance_path in entry.instance_paths:
        record = record_cache.get(instance_path)
        if record is None:
            continue
        score = (
            record.confidence,
            record.trajectory_effect.case_score,
            record.created_at,
        )
        if best_score is None or score > best_score:
            best_path = instance_path
            best_record = record
            best_score = score
    if best_record is not None:
        return best_path, best_record
    return (entry.instance_paths[-1] if entry.instance_paths else None), None


def _classification_key(record: GenericOrchestrationExperienceRecord) -> str:
    classification = record.problem_classification
    return "__".join(
        [
            _slug_token(classification.intent),
            _slug_token(classification.evidence_mode),
            _slug_token(classification.scope),
        ]
    )


def _entry_id(*, classification: str, abstraction: str) -> str:
    digest = hashlib.sha1(f"{classification}\n{abstraction}".encode("utf-8")).hexdigest()[:8]
    return f"{classification}__{digest}"


def _slug_token(value: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip().casefold()).strip("_")
    return compact or "unknown"


def _instance_path(path: Path, *, root: Path | None) -> str:
    base = root or repo_root()
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _strategy_explain_for_records(records: list[GenericOrchestrationExperienceRecord]) -> str:
    if not records:
        return "Strategy: keep the graph bounded, collect enough evidence, then synthesize once."
    representative = max(
        records,
        key=lambda record: (
            record.confidence,
            record.trajectory_effect.case_score,
            record.created_at,
        ),
    )
    classification = representative.problem_classification
    trajectories = [record.trajectory for record in records]
    effects = [record.trajectory_effect for record in records]
    graph_shapes = sorted({item.graph_shape for item in trajectories if item.graph_shape})
    node_counts = [item.node_count for item in trajectories if item.node_count > 0]
    median_node_count = sorted(node_counts)[len(node_counts) // 2] if node_counts else 0
    min_evidence = min((item.evidence_score for item in effects), default=0.0)

    parts = [
        _intent_strategy_sentence(classification),
        _evidence_strategy_sentence(classification, representative.problem_abstraction),
        _graph_strategy_sentence(graph_shapes=graph_shapes, median_node_count=median_node_count),
        _answer_strategy_sentence(representative),
    ]
    risk = _risk_strategy_sentence(
        classification=classification,
        records=records,
        min_evidence=min_evidence,
    )
    if risk:
        parts.append(risk)
    return " ".join(part for part in parts if part)


def _intent_strategy_sentence(classification: ProblemClassification) -> str:
    if classification.intent == "local_code_explanation":
        return (
            "Strategy: use one bounded repo-inspection lane to find the exact "
            "code paths or run artifacts that answer the question, then do a "
            "single synthesis pass."
        )
    if classification.intent == "evidence_judgment":
        return (
            "Strategy: frame the task as a bounded repo-local judgment: inspect "
            "only the artifacts needed to support or reject the claim, then state "
            "the decision and its limits."
        )
    if classification.intent == "computed_judgment":
        return (
            "Strategy: make the local computation lane explicit before synthesis "
            "so the final judgment is tied to computed evidence, not hidden "
            "reasoning."
        )
    if classification.intent == "repo_repair":
        return (
            "Strategy: inspect the failing local path, apply the smallest concrete "
            "repair, verify it, then summarize the fix evidence."
        )
    return (
        "Strategy: choose the smallest generic graph that still creates a visible "
        "evidence step before the final answer."
    )


def _evidence_strategy_sentence(
    classification: ProblemClassification,
    abstraction: ProblemAbstraction,
) -> str:
    if classification.evidence_mode == "local_only":
        return (
            "Keep evidence local; stop once the necessary repository files, tests, "
            "or orchestration artifacts have been read, and avoid web discovery or "
            "report-style expansion unless the user asks for it."
        )
    if classification.evidence_mode == "computed_local":
        return (
            "Use local artifacts and operator outputs as the evidence source, and "
            "separate computed values from the final interpretation."
        )
    if classification.evidence_mode == "trusted_web":
        return (
            "Use a small set of trusted sources, fetch concrete pages after search, "
            "and separate source-backed facts from inference."
        )
    if "evidence_boundary" in abstraction.constraints:
        return (
            "Make the evidence boundary explicit so the answer distinguishes direct "
            "evidence, inference, and remaining uncertainty."
        )
    return "Collect only the evidence needed for one bounded synthesis."


def _graph_strategy_sentence(*, graph_shapes: list[str], median_node_count: int) -> str:
    shape_text = ", ".join(graph_shapes) if graph_shapes else "unknown"
    if median_node_count and median_node_count <= 4:
        return (
            f"Observed successful shape: {shape_text} with about "
            f"{median_node_count} nodes; prefer init -> one evidence worker -> "
            "summarize/final response instead of parallel lanes."
        )
    if median_node_count:
        return (
            f"Observed successful shape: {shape_text} with about "
            f"{median_node_count} nodes; use multiple evidence lanes only when "
            "the task truly has separable evidence needs."
        )
    return (
        f"Observed successful shape: {shape_text}; keep the graph compact and "
        "reserve extra lanes for clearly separable evidence needs."
    )


def _answer_strategy_sentence(record: GenericOrchestrationExperienceRecord) -> str:
    constraints = set(record.problem_abstraction.constraints)
    if "short_answer" in constraints or record.trajectory.answer_style == "short_direct_answer":
        return (
            "Because the prompt asks for a compact answer, put the conclusion "
            "first and include only the minimum evidence boundary needed to make "
            "the claim auditable."
        )
    if record.trajectory.answer_style == "oral_or_conversational":
        return (
            "Keep the final answer conversational, but still name the evidence "
            "basis and separate what is directly supported from what is inferred."
        )
    return (
        "The final answer should name the evidence basis and avoid unsupported "
        "certainty."
    )


def _risk_strategy_sentence(
    *,
    classification: ProblemClassification,
    records: list[GenericOrchestrationExperienceRecord],
    min_evidence: float,
) -> str:
    risks: list[str] = []
    if min_evidence and min_evidence < 70:
        risks.append(
            "observed evidence scores were sometimes weak, so explicitly cite the "
            "specific artifacts used and avoid overclaiming"
        )
    if classification.evidence_mode == "local_only" and any(
        record.trajectory_effect.source_url_count > 0
        for record in records
    ):
        risks.append(
            "local-only tasks should not invent or rely on external source URLs"
        )
    if any(record.trajectory.tool_rhythm in {"moderate", "heavy"} for record in records):
        risks.append(
            "watch for over-orchestration when the user only wants a short local answer"
        )
    if not risks:
        return ""
    return "Risk control: " + "; ".join(risks) + "."


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
