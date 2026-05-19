"""Core models and config loading for the generic orchestration harness."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
class GenericCase:
    case_id: str
    prompt: str
    split: str
    weight: float
    max_runtime_minutes: int


@dataclass(frozen=True)
class Experiment:
    path: Path
    name: str
    output_root: Path
    max_iterations: int
    max_parallel_cases: int
    proposer_command: tuple[str, ...] | None
    proposer_max_runtime_minutes: int
    surfaces: dict[str, Surface]
    cases: tuple[GenericCase, ...]

    def cases_for_split(self, split: str) -> list[GenericCase]:
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
    case_id: str
    split: str
    weight: float
    status: str
    returncode: int
    completion_status: str
    completion_level: str
    overall_score: float
    component_scores: dict[str, float]
    findings: tuple[str, ...]
    run_dir: str
    generic_trace_summary_path: str
    evaluation_path: str
    stdout_path: str
    stderr_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitScore:
    split: str
    variant: str
    mean_score: float
    total_weight: float
    component_means: dict[str, float]
    outcomes: tuple[CaseScoreResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "split": self.split,
            "variant": self.variant,
            "mean_score": self.mean_score,
            "total_weight": self.total_weight,
            "component_means": self.component_means,
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
            "output_root": str(experiment.output_root),
            "max_iterations": experiment.max_iterations,
            "max_parallel_cases": experiment.max_parallel_cases,
            "proposer_mode": experiment.proposer_mode,
            "proposer_command": None
            if experiment.proposer_command is None
            else list(experiment.proposer_command),
            "surfaces": [asdict(surface) for surface in experiment.surfaces.values()],
            "cases": [asdict(case) for case in experiment.cases],
        }
        (self.run_root / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_iteration_decision(
        self,
        *,
        iteration: int,
        starting_variant: str,
        candidate: CandidateEvaluation,
    ) -> None:
        iteration_dir = self.iteration_dir(iteration)
        iteration_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "iteration": iteration,
            "starting_variant": starting_variant,
            "candidate_variant": candidate.variant,
            "decision": "accepted" if candidate.accepted else "rejected",
            "reason": candidate.reason,
            "proposal": candidate.proposal.to_dict(),
            "train_mean_score": candidate.train.mean_score,
            "holdout_mean_score": candidate.holdout.mean_score,
        }
        (iteration_dir / "decision.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_report(self, report: RunReport) -> None:
        report.write(self.run_root)


def load_experiment(path: Path) -> Experiment:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    experiment_cfg = payload["experiment"]
    proposer_cfg = payload.get("proposer", {})
    surface_cfg = payload.get("surfaces", {})
    cases_cfg = payload.get("cases", [])

    surfaces: dict[str, Surface] = {}
    for name, data in surface_cfg.items():
        kind = str(data["kind"])
        if kind not in VALID_SURFACE_KINDS:
            raise ValueError(f"unsupported surface kind: {kind}")
        filename = str(data.get("filename") or Path(str(data["target"])).name)
        if "base_file" in data:
            base_value = resolve_repo_path(str(data["base_file"])).read_text(encoding="utf-8")
        else:
            base_value = str(data["base_value"])
        surfaces[name] = Surface(
            name=name,
            kind=kind,
            target=str(data["target"]),
            filename=filename,
            base_value=base_value,
        )

    cases: list[GenericCase] = []
    for item in cases_cfg:
        split = str(item["split"])
        if split not in VALID_SPLITS:
            raise ValueError(f"unsupported split: {split}")
        cases.append(
            GenericCase(
                case_id=str(item["case_id"]),
                prompt=str(item["prompt"]),
                split=split,
                weight=float(item.get("weight", 1.0)),
                max_runtime_minutes=int(item.get("max_runtime_minutes", 10)),
            )
        )

    proposer_command = None
    if "command" in proposer_cfg:
        proposer_command = resolve_command_tokens(list(proposer_cfg["command"]))

    return Experiment(
        path=path,
        name=str(experiment_cfg["name"]),
        output_root=resolve_repo_path(str(experiment_cfg["output_root"])),
        max_iterations=int(experiment_cfg.get("max_iterations", 1)),
        max_parallel_cases=int(experiment_cfg.get("max_parallel_cases", 1)),
        proposer_command=proposer_command,
        proposer_max_runtime_minutes=int(proposer_cfg.get("max_runtime_minutes", 10)),
        surfaces=surfaces,
        cases=tuple(cases),
    )
