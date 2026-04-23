"""Core models and config loading for the complex QA harness."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.skill_tests.runner import LiveEvalCase, load_batch_cases


VALID_SPLITS = ("train", "holdout", "scorecard")
VISIBLE_SPLITS = {"train"}
VALID_SURFACE_KINDS = {"workspace_file"}
ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def expand_env(value: str) -> str:
    return ENV_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def resolve_repo_path(raw: str) -> Path:
    path = Path(expand_env(raw)).expanduser()
    return path if path.is_absolute() else repo_root() / path


def resolve_command_tokens(tokens: list[str]) -> tuple[str, ...]:
    resolved: list[str] = []
    for token in tokens:
        expanded = expand_env(token)
        candidate = resolve_repo_path(expanded)
        if ("/" in expanded or expanded.endswith(".py")) and candidate.exists():
            resolved.append(str(candidate))
        else:
            resolved.append(expanded)
    return tuple(resolved)


def utc_stamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def safe_slug(value: str) -> str:
    slug = SLUG_PATTERN.sub("_", value).strip("_")
    return slug or "item"


@dataclass(frozen=True)
class Surface:
    name: str
    kind: str
    target: str
    filename: str
    base_value: str


@dataclass(frozen=True)
class ComplexQACase:
    case_name: str
    split: str
    weight: float
    live_eval_case: LiveEvalCase


@dataclass(frozen=True)
class Experiment:
    path: Path
    name: str
    batch_file: Path
    output_root: Path
    max_iterations: int
    max_parallel_cases: int
    proposer_command: tuple[str, ...] | None
    proposer_max_runtime_minutes: int
    surfaces: dict[str, Surface]
    cases: tuple[ComplexQACase, ...]

    def cases_for_split(self, split: str) -> list[ComplexQACase]:
        return [case for case in self.cases if case.split == split]

    def has_split(self, split: str) -> bool:
        return bool(self.cases_for_split(split))

    def has_proposer(self) -> bool:
        return self.proposer_command is not None

    @property
    def proposer_mode(self) -> str | None:
        return "command" if self.proposer_command is not None else None


@dataclass(frozen=True)
class Variant:
    label: str
    changed_surfaces: tuple[str, ...]
    values: dict[str, str]

    @property
    def key(self) -> str:
        return self.label

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "changed_surfaces": list(self.changed_surfaces),
            "values": self.values,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class CaseScoreResult:
    case_name: str
    split: str
    weight: float
    status: str
    overall_score: float
    rule_score: float
    judge_score: float
    answer_path: str
    trace_path: str
    judge_path: str
    log_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitScore:
    split: str
    variant: str
    mean_score: float
    total_weight: float
    outcomes: tuple[CaseScoreResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "split": self.split,
            "variant": self.variant,
            "mean_score": self.mean_score,
            "total_weight": self.total_weight,
            "outcomes": [item.to_dict() for item in self.outcomes],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class Proposal:
    changed_surfaces: tuple[str, ...]
    workspace_dir: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateEvaluation:
    variant: str
    proposal: Proposal
    train: SplitScore
    holdout: SplitScore
    accepted: bool
    reason: str


@dataclass(frozen=True)
class IterationRecord:
    iteration: int
    starting_variant: str
    candidate: CandidateEvaluation | None


@dataclass(frozen=True)
class RunReport:
    created_at: str
    config_path: str
    run_root: str
    proposer_mode: str | None
    baseline: Variant
    final: Variant
    baseline_train: SplitScore
    baseline_holdout: SplitScore | None
    final_train: SplitScore
    final_holdout: SplitScore | None
    iterations: tuple[IterationRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "config_path": self.config_path,
            "run_root": self.run_root,
            "proposer_mode": self.proposer_mode,
            "baseline": self.baseline.to_dict(),
            "final": self.final.to_dict(),
            "baseline_train": self.baseline_train.to_dict(),
            "baseline_holdout": None
            if self.baseline_holdout is None
            else self.baseline_holdout.to_dict(),
            "final_train": self.final_train.to_dict(),
            "final_holdout": None
            if self.final_holdout is None
            else self.final_holdout.to_dict(),
            "iterations": [
                {
                    "iteration": iteration.iteration,
                    "starting_variant": iteration.starting_variant,
                    "candidate": None
                    if iteration.candidate is None
                    else {
                        "variant": iteration.candidate.variant,
                        "proposal": iteration.candidate.proposal.to_dict(),
                        "accepted": iteration.candidate.accepted,
                        "reason": iteration.candidate.reason,
                        "train": iteration.candidate.train.to_dict(),
                        "holdout": iteration.candidate.holdout.to_dict(),
                    },
                }
                for iteration in self.iterations
            ],
        }

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class RunLayout:
    def __init__(self, *, output_root: Path, experiment_name: str, run_id: str | None = None) -> None:
        self.output_root = output_root
        self.experiment_name = experiment_name
        self.run_id = run_id or utc_stamp()
        self.run_root = self.output_root / experiment_name / self.run_id

    @property
    def variants_dir(self) -> Path:
        return self.run_root / "variants"

    @property
    def visible_root(self) -> Path:
        return self.run_root / "history" / "visible"

    @property
    def private_root(self) -> Path:
        return self.run_root / "history" / "private"

    @property
    def visible_iterations_dir(self) -> Path:
        return self.visible_root / "iterations"

    def variant_path(self, label: str) -> Path:
        return self.variants_dir / f"{label}.json"

    def split_dir(self, *, variant: str, split: str) -> Path:
        base = self.visible_root if split in VISIBLE_SPLITS else self.private_root
        return base / split / variant

    def iteration_dir(self, iteration: int) -> Path:
        return self.visible_iterations_dir / f"{iteration:03d}"

    def proposer_workspace_dir(self, iteration: int) -> Path:
        return self.iteration_dir(iteration) / "proposer_workspace"

    def write_manifest(self, experiment: Experiment) -> None:
        self.run_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": experiment.name,
            "batch_file": str(experiment.batch_file),
            "output_root": str(experiment.output_root),
            "max_iterations": experiment.max_iterations,
            "max_parallel_cases": experiment.max_parallel_cases,
            "proposer_mode": experiment.proposer_mode,
            "proposer_command": None
            if experiment.proposer_command is None
            else list(experiment.proposer_command),
            "surfaces": [asdict(surface) for surface in experiment.surfaces.values()],
            "cases": [
                {
                    "case_name": case.case_name,
                    "split": case.split,
                    "weight": case.weight,
                    "live_eval_case": {
                        "name": case.live_eval_case.name,
                        "path": str(case.live_eval_case.path),
                    },
                }
                for case in experiment.cases
            ],
        }
        (self.run_root / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_report(self, report: RunReport) -> None:
        report.write(self.run_root)

    def write_iteration_decision(
        self,
        *,
        iteration: int,
        starting_variant: str,
        candidate: CandidateEvaluation,
    ) -> None:
        iteration_dir = self.iteration_dir(iteration)
        iteration_dir.mkdir(parents=True, exist_ok=True)
        decision = "accepted" if candidate.accepted else "rejected"
        payload = {
            "iteration": iteration,
            "starting_variant": starting_variant,
            "candidate_variant": candidate.variant,
            "decision": decision,
            "reason": candidate.reason,
            "changed_surfaces": list(candidate.proposal.changed_surfaces),
            "proposal_summary": candidate.proposal.summary,
            "train_mean_score": candidate.train.mean_score,
            "holdout_mean_score": candidate.holdout.mean_score,
        }
        (iteration_dir / "decision.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _load_surface(name: str, payload: dict[str, Any]) -> Surface:
    kind = str(payload["kind"])
    if kind not in VALID_SURFACE_KINDS:
        raise ValueError(f"invalid surface kind for {name}: {kind}")
    if "base_file" in payload:
        base_path = resolve_repo_path(str(payload["base_file"]))
        base_value = base_path.read_text(encoding="utf-8")
    elif "base_value" in payload:
        base_value = str(payload["base_value"])
    else:
        raise ValueError(f"surface {name} must define base_file or base_value")
    return Surface(
        name=name,
        kind=kind,
        target=str(payload["target"]),
        filename=str(payload["filename"]),
        base_value=base_value,
    )


def load_experiment(path: Path) -> Experiment:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    experiment_payload = payload["experiment"]
    surfaces = {
        name: _load_surface(name, surface_payload)
        for name, surface_payload in payload.get("surfaces", {}).items()
    }
    if not surfaces:
        raise ValueError("experiment must define at least one surface")

    batch_file = resolve_repo_path(str(experiment_payload["batch_file"]))
    available_cases = {case.name: case for case in load_batch_cases(batch_file)}
    case_entries: list[ComplexQACase] = []
    for item in payload.get("cases", []):
        split = str(item["split"])
        if split not in VALID_SPLITS:
            raise ValueError(f"invalid split {split}")
        case_name = str(item["case_name"])
        if case_name not in available_cases:
            raise ValueError(f"unknown batch case {case_name}")
        weight = float(item.get("weight", 1.0))
        if weight <= 0:
            raise ValueError("case weight must be > 0")
        case_entries.append(
            ComplexQACase(
                case_name=case_name,
                split=split,
                weight=weight,
                live_eval_case=available_cases[case_name],
            )
        )
    if not case_entries:
        raise ValueError("experiment must define at least one case")

    proposer = payload.get("proposer", {})
    proposer_command = None
    raw_command = proposer.get("command")
    if raw_command:
        proposer_command = resolve_command_tokens([str(token) for token in raw_command])

    return Experiment(
        path=path,
        name=str(experiment_payload["name"]),
        batch_file=batch_file,
        output_root=resolve_repo_path(str(experiment_payload["output_root"])),
        max_iterations=int(experiment_payload.get("max_iterations", 3)),
        max_parallel_cases=int(experiment_payload.get("max_parallel_cases", 4)),
        proposer_command=proposer_command,
        proposer_max_runtime_minutes=int(proposer.get("max_runtime_minutes", 10)),
        surfaces=surfaces,
        cases=tuple(case_entries),
    )
