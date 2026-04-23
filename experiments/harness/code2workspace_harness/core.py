"""Core config, data model, and run layout for the local harness."""

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
    """Return the repository root."""
    return Path(__file__).resolve().parents[3]


def expand_env(value: str) -> str:
    """Expand `${ENV_VAR}` references in config values."""
    return ENV_PATTERN.sub(lambda match: os.environ[match.group(1)], value)


def resolve_repo_path(raw: str) -> Path:
    """Resolve one repository-relative path."""
    path = Path(expand_env(raw)).expanduser()
    return path if path.is_absolute() else repo_root() / path


def resolve_command_tokens(tokens: list[str]) -> tuple[str, ...]:
    """Resolve command tokens that point at local repo files."""
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
    """Return one filesystem-safe UTC timestamp."""
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def safe_slug(value: str) -> str:
    """Return a filesystem-safe slug."""
    slug = SLUG_PATTERN.sub("_", value).strip("_")
    return slug or "item"


@dataclass(frozen=True)
class Surface:
    """One editable harness surface."""

    name: str
    kind: str
    target: str
    filename: str
    base_value: str


@dataclass(frozen=True)
class EvalCase:
    """One explicit repository-level harness case."""

    case_id: str
    repo_url: str
    split: str
    max_runtime_minutes: int


@dataclass(frozen=True)
class Experiment:
    """Loaded harness experiment."""

    path: Path
    name: str
    workspace_root: Path
    output_root: Path
    max_iterations: int
    proposer_command: tuple[str, ...] | None
    proposer_max_runtime_minutes: int
    better_agent_model: str | None
    better_agent_max_turns: int
    better_agent_system_prompt: str | None
    better_agent_deepagents_root: Path | None
    surfaces: dict[str, Surface]
    cases: tuple[EvalCase, ...]

    def cases_for_split(self, split: str) -> list[EvalCase]:
        """Return cases for one split."""
        return [case for case in self.cases if case.split == split]

    def has_split(self, split: str) -> bool:
        """Return whether the experiment defines one split."""
        return bool(self.cases_for_split(split))

    def has_proposer(self) -> bool:
        """Return whether any outer-loop proposer is configured."""
        return self.proposer_command is not None or self.better_agent_model is not None

    @property
    def proposer_mode(self) -> str | None:
        """Return the configured proposer mode."""
        if self.proposer_command is not None:
            return "command"
        if self.better_agent_model is not None:
            return "deepagents"
        return None


@dataclass(frozen=True)
class Variant:
    """Materialized surface variant."""

    label: str
    changed_surfaces: tuple[str, ...]
    values: dict[str, str]

    @property
    def key(self) -> str:
        """Return the stable filesystem key for this variant."""
        return self.label

    def to_dict(self) -> dict[str, Any]:
        """Serialize one variant."""
        return {
            "label": self.label,
            "changed_surfaces": list(self.changed_surfaces),
            "values": self.values,
        }

    def save(self, path: Path) -> None:
        """Persist one variant."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> Variant:
        """Load one variant from disk."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            label=str(payload["label"]),
            changed_surfaces=tuple(str(item) for item in payload["changed_surfaces"]),
            values={name: str(value) for name, value in payload["values"].items()},
        )


@dataclass(frozen=True)
class CaseResult:
    """One harness case result."""

    case_id: str
    repo_url: str
    split: str
    status: str
    completed: bool
    returncode: int
    run_dir: str
    summary_path: str
    manifest_path: str
    error_message: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether the case counts as passed."""
        return self.completed and self.status == "completed"


@dataclass(frozen=True)
class SplitResult:
    """Aggregate result for one split."""

    split: str
    variant: str
    passed: int
    total: int
    outcomes: tuple[CaseResult, ...]

    @property
    def correctness(self) -> float:
        """Return pass rate for the split."""
        return 0.0 if self.total == 0 else self.passed / self.total

    def failing_outcomes(self) -> list[CaseResult]:
        """Return failed or incomplete outcomes."""
        return [outcome for outcome in self.outcomes if not outcome.passed]

    def to_dict(self) -> dict[str, Any]:
        """Serialize one split result."""
        return {
            "split": self.split,
            "variant": self.variant,
            "passed": self.passed,
            "total": self.total,
            "correctness": self.correctness,
            "outcomes": [asdict(item) for item in self.outcomes],
        }

    def save(self, path: Path) -> None:
        """Persist one split result."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class Proposal:
    """One outer-loop proposal."""

    changed_surfaces: tuple[str, ...]
    workspace_dir: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize one proposal."""
        return asdict(self)


@dataclass(frozen=True)
class CandidateEvaluation:
    """One candidate evaluation."""

    variant: str
    proposal: Proposal
    train: SplitResult
    holdout: SplitResult
    accepted: bool
    reason: str


@dataclass(frozen=True)
class IterationRecord:
    """One optimization iteration."""

    iteration: int
    starting_variant: str
    candidate: CandidateEvaluation | None


@dataclass(frozen=True)
class RunReport:
    """Final run report."""

    created_at: str
    config_path: str
    run_root: str
    proposer_mode: str | None
    baseline: Variant
    final: Variant
    baseline_train: SplitResult
    baseline_holdout: SplitResult
    final_train: SplitResult
    final_holdout: SplitResult
    baseline_scorecard: SplitResult | None
    final_scorecard: SplitResult | None
    iterations: tuple[IterationRecord, ...]

    @property
    def baseline_combined_passed(self) -> int:
        """Return baseline train + holdout passed count."""
        return self.baseline_train.passed + self.baseline_holdout.passed

    @property
    def baseline_combined_total(self) -> int:
        """Return baseline train + holdout total case count."""
        return self.baseline_train.total + self.baseline_holdout.total

    @property
    def final_combined_passed(self) -> int:
        """Return final train + holdout passed count."""
        return self.final_train.passed + self.final_holdout.passed

    @property
    def final_combined_total(self) -> int:
        """Return final train + holdout total case count."""
        return self.final_train.total + self.final_holdout.total

    @property
    def combined_delta(self) -> int:
        """Return final minus baseline combined pass count."""
        return self.final_combined_passed - self.baseline_combined_passed

    def architecture_effect_summary(self) -> list[str]:
        """Return short plain-language statements for report readers."""
        mode = self.proposer_mode or "none"
        lines = [
            (
                "This run optimized the existing one-shot runner through an outer-loop "
                f"`{mode}` proposer instead of replacing the inner execution path."
            ),
            (
                "The architecture keeps the optimization target narrow: it edits only "
                "explicit harness surfaces, then measures the result on the same train "
                "and holdout repositories."
            ),
        ]
        if self.combined_delta > 0:
            lines.append(
                (
                    "In this run, that architecture produced a measurable gain: combined "
                    f"train + holdout passes moved from `{self.baseline_combined_passed}/"
                    f"{self.baseline_combined_total}` to `{self.final_combined_passed}/"
                    f"{self.final_combined_total}`, a delta of `+{self.combined_delta}`."
                )
            )
        elif self.combined_delta == 0:
            lines.append(
                (
                    "In this run, the architecture did not increase combined train + "
                    "holdout passes yet, but it still produced auditable candidate edits, "
                    "serialized decisions, and a clear record of what failed to improve."
                )
            )
        else:
            lines.append(
                (
                    "This run ended worse than baseline, which is precisely why the "
                    "keep/discard rule matters: the architecture makes regressions visible "
                    "and rejectable instead of silently shipping them."
                )
            )
        return lines

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report."""
        return {
            "created_at": self.created_at,
            "config_path": self.config_path,
            "run_root": self.run_root,
            "proposer_mode": self.proposer_mode,
            "baseline": self.baseline.to_dict(),
            "final": self.final.to_dict(),
            "baseline_combined_passed": self.baseline_combined_passed,
            "baseline_combined_total": self.baseline_combined_total,
            "final_combined_passed": self.final_combined_passed,
            "final_combined_total": self.final_combined_total,
            "combined_delta": self.combined_delta,
            "architecture_effect_summary": self.architecture_effect_summary(),
            "baseline_train": self.baseline_train.to_dict(),
            "baseline_holdout": self.baseline_holdout.to_dict(),
            "final_train": self.final_train.to_dict(),
            "final_holdout": self.final_holdout.to_dict(),
            "baseline_scorecard": None
            if self.baseline_scorecard is None
            else self.baseline_scorecard.to_dict(),
            "final_scorecard": None
            if self.final_scorecard is None
            else self.final_scorecard.to_dict(),
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

    def to_markdown(self) -> str:
        """Render a concise Markdown report."""
        lines = [
            "# code2workspace harness report",
            "",
            f"- Proposer mode: `{self.proposer_mode or 'none'}`",
            f"- Baseline changed surfaces: `{', '.join(self.baseline.changed_surfaces) or 'none'}`",
            f"- Final changed surfaces: `{', '.join(self.final.changed_surfaces) or 'none'}`",
            f"- Combined train + holdout: `{self.baseline_combined_passed}/{self.baseline_combined_total}` -> `{self.final_combined_passed}/{self.final_combined_total}`",
            f"- Combined pass delta: `{self.combined_delta:+d}`",
            "",
            "| Split | Baseline | Final |",
            "| --- | --- | --- |",
            f"| Train | `{self.baseline_train.passed}/{self.baseline_train.total}` | `{self.final_train.passed}/{self.final_train.total}` |",
            f"| Holdout | `{self.baseline_holdout.passed}/{self.baseline_holdout.total}` | `{self.final_holdout.passed}/{self.final_holdout.total}` |",
        ]
        if self.baseline_scorecard is not None and self.final_scorecard is not None:
            lines.append(
                f"| Scorecard | `{self.baseline_scorecard.passed}/{self.baseline_scorecard.total}` | `{self.final_scorecard.passed}/{self.final_scorecard.total}` |"
            )
        lines.extend(["", "## What This Architecture Changed", ""])
        lines.extend(f"- {line}" for line in self.architecture_effect_summary())
        lines.extend(["", "## Iterations", ""])
        for iteration in self.iterations:
            if iteration.candidate is None:
                lines.append(f"- Iteration {iteration.iteration}: no candidate produced")
                continue
            candidate = iteration.candidate
            decision = "accepted" if candidate.accepted else "rejected"
            lines.extend(
                [
                    f"- Iteration {iteration.iteration}: {decision} `{candidate.variant}`",
                    f"  - Train: `{candidate.train.passed}/{candidate.train.total}`",
                    f"  - Holdout: `{candidate.holdout.passed}/{candidate.holdout.total}`",
                    f"  - Changed surfaces: `{', '.join(candidate.proposal.changed_surfaces) or 'none'}`",
                    f"  - Reason: {candidate.reason}",
                ]
            )
        lines.append("")
        return "\n".join(lines)

    def write(self, output_dir: Path) -> None:
        """Write JSON and Markdown reports."""
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "report.md").write_text(self.to_markdown(), encoding="utf-8")


class RunLayout:
    """Filesystem layout for one harness run."""

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
        """Return one variant path."""
        return self.variants_dir / f"{label}.json"

    def split_dir(self, *, variant: str, split: str) -> Path:
        """Return one split output directory."""
        base = self.visible_root if split in VISIBLE_SPLITS else self.private_root
        return base / split / variant

    def proposer_workspace_dir(self, iteration: int) -> Path:
        """Return the proposer workspace directory for one iteration."""
        return self.visible_iterations_dir / f"{iteration:03d}" / "proposer_workspace"

    def iteration_dir(self, iteration: int) -> Path:
        """Return the root directory for one iteration."""
        return self.visible_iterations_dir / f"{iteration:03d}"

    def write_manifest(self, experiment: Experiment) -> None:
        """Persist the run-level manifest and split inventory."""
        self.run_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": experiment.name,
            "workspace_root": str(experiment.workspace_root),
            "output_root": str(experiment.output_root),
            "max_iterations": experiment.max_iterations,
            "proposer_mode": experiment.proposer_mode,
            "proposer_command": None
            if experiment.proposer_command is None
            else list(experiment.proposer_command),
            "proposer_max_runtime_minutes": experiment.proposer_max_runtime_minutes,
            "better_agent": None
            if experiment.better_agent_model is None
            else {
                "model": experiment.better_agent_model,
                "max_turns": experiment.better_agent_max_turns,
                "system_prompt": experiment.better_agent_system_prompt,
                "deepagents_root": None
                if experiment.better_agent_deepagents_root is None
                else str(experiment.better_agent_deepagents_root),
            },
            "surfaces": [asdict(surface) for surface in experiment.surfaces.values()],
            "cases": [asdict(case) for case in experiment.cases],
        }
        (self.run_root / "manifest.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_split_manifest(experiment, self.run_root)

    def write_iteration_decision(
        self,
        *,
        iteration: int,
        starting_variant: str,
        candidate: CandidateEvaluation,
    ) -> None:
        """Persist one keep/discard decision."""
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
            "train_passed": candidate.train.passed,
            "train_total": candidate.train.total,
            "holdout_passed": candidate.holdout.passed,
            "holdout_total": candidate.holdout.total,
        }
        (iteration_dir / "decision.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        lines = [
            f"# Iteration {iteration}",
            "",
            f"- Starting variant: `{starting_variant}`",
            f"- Candidate variant: `{candidate.variant}`",
            f"- Decision: `{decision}`",
            f"- Train: `{candidate.train.passed}/{candidate.train.total}`",
            f"- Holdout: `{candidate.holdout.passed}/{candidate.holdout.total}`",
            f"- Changed surfaces: `{', '.join(candidate.proposal.changed_surfaces) or 'none'}`",
            f"- Reason: {candidate.reason}",
            "",
            "## Proposal Summary",
            "",
            candidate.proposal.summary or "_No proposal summary written._",
            "",
        ]
        (iteration_dir / "decision.md").write_text("\n".join(lines), encoding="utf-8")

    def write_report(self, report: RunReport) -> None:
        """Write the final run report."""
        report.write(self.run_root)


def _load_surface(name: str, payload: dict[str, Any]) -> Surface:
    kind = str(payload["kind"])
    if kind not in VALID_SURFACE_KINDS:
        msg = f"invalid surface kind for {name}: {kind}"
        raise ValueError(msg)
    if "base_file" in payload:
        base_path = resolve_repo_path(str(payload["base_file"]))
        base_value = base_path.read_text(encoding="utf-8")
    elif "base_value" in payload:
        base_value = str(payload["base_value"])
    else:
        msg = f"surface {name} must define base_file or base_value"
        raise ValueError(msg)
    return Surface(
        name=name,
        kind=kind,
        target=str(payload["target"]),
        filename=str(payload["filename"]),
        base_value=base_value,
    )


def _load_case(payload: dict[str, Any]) -> EvalCase:
    split = str(payload["split"])
    if split not in VALID_SPLITS:
        msg = f"invalid split {split}"
        raise ValueError(msg)
    return EvalCase(
        case_id=str(payload["case_id"]),
        repo_url=str(payload["repo_url"]),
        split=split,
        max_runtime_minutes=int(payload.get("max_runtime_minutes", 30)),
    )


def _repo_name_from_url(repo_url: str) -> str:
    cleaned = repo_url.rstrip("/")
    name = cleaned.rsplit("/", 1)[-1]
    return name.removesuffix(".git")


def _load_cases_from_repo_splits(
    *,
    splits_path: Path,
    default_max_runtime_minutes: int,
    runtime_overrides: dict[str, int],
) -> tuple[EvalCase, ...]:
    payload = tomllib.loads(splits_path.read_text(encoding="utf-8"))
    raw_splits = payload.get("splits", {})
    cases: list[EvalCase] = []
    for split in VALID_SPLITS:
        for repo_url in raw_splits.get(split, []):
            repo = _repo_name_from_url(str(repo_url))
            max_runtime_minutes = runtime_overrides.get(repo, default_max_runtime_minutes)
            cases.append(
                EvalCase(
                    case_id=f"{repo}-{split}",
                    repo_url=str(repo_url),
                    split=split,
                    max_runtime_minutes=max_runtime_minutes,
                )
            )
    return tuple(cases)


def load_experiment(path: Path) -> Experiment:
    """Load one experiment config."""
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    experiment = payload["experiment"]
    proposer = payload.get("proposer", {})
    better_agent = payload.get("better_agent", {})
    surfaces = {
        name: _load_surface(name, surface_payload)
        for name, surface_payload in payload.get("surfaces", {}).items()
    }
    raw_runtime_overrides = payload.get("repo_case_runtime_minutes", {})
    runtime_overrides = {
        str(repo): int(minutes)
        for repo, minutes in raw_runtime_overrides.items()
    }
    raw_cases = payload.get("cases", [])
    raw_repo_splits = experiment.get("repo_splits")
    if raw_cases and raw_repo_splits:
        raise ValueError("configure either [[cases]] or [experiment].repo_splits, not both")
    if raw_repo_splits:
        cases = _load_cases_from_repo_splits(
            splits_path=resolve_repo_path(str(raw_repo_splits)),
            default_max_runtime_minutes=int(experiment.get("default_max_runtime_minutes", 30)),
            runtime_overrides=runtime_overrides,
        )
    else:
        cases = tuple(_load_case(item) for item in raw_cases)
    if not cases:
        raise ValueError("experiment must define at least one case")
    if not surfaces:
        raise ValueError("experiment must define at least one surface")
    max_iterations = int(experiment.get("max_iterations", 3))
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    proposer_command = None
    raw_command = proposer.get("command")
    if raw_command and better_agent:
        raise ValueError("configure either [proposer].command or [better_agent], not both")
    if raw_command:
        proposer_command = resolve_command_tokens([str(token) for token in raw_command])
    better_agent_model = None
    better_agent_max_turns = 40
    better_agent_system_prompt = None
    better_agent_deepagents_root = None
    if better_agent:
        better_agent_model = str(better_agent["model"])
        better_agent_max_turns = int(better_agent.get("max_turns", 40))
        if better_agent_max_turns < 1:
            raise ValueError("better_agent.max_turns must be at least 1")
        if raw_root := better_agent.get("deepagents_root"):
            better_agent_deepagents_root = resolve_repo_path(str(raw_root))
        raw_system_prompt = str(better_agent.get("system_prompt", "")).strip()
        better_agent_system_prompt = raw_system_prompt or None
    return Experiment(
        path=path,
        name=str(experiment["name"]),
        workspace_root=resolve_repo_path(str(experiment["workspace_root"])),
        output_root=resolve_repo_path(str(experiment["output_root"])),
        max_iterations=max_iterations,
        proposer_command=proposer_command,
        proposer_max_runtime_minutes=int(proposer.get("max_runtime_minutes", 10)),
        better_agent_model=better_agent_model,
        better_agent_max_turns=better_agent_max_turns,
        better_agent_system_prompt=better_agent_system_prompt,
        better_agent_deepagents_root=better_agent_deepagents_root,
        surfaces=surfaces,
        cases=cases,
    )


def write_split_manifest(experiment: Experiment, output_dir: Path) -> None:
    """Write split manifests for the current experiment."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        split: [asdict(case) for case in experiment.cases_for_split(split)]
        for split in VALID_SPLITS
        if experiment.cases_for_split(split)
    }
    (output_dir / "split.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = ["# Split Manifest", ""]
    for split, items in payload.items():
        lines.extend([f"## {split.title()}", ""])
        lines.extend(
            f"- `{item['case_id']}` -> `{item['repo_url']}` ({item['max_runtime_minutes']} min)"
            for item in items
        )
        lines.append("")
    (output_dir / "split.md").write_text("\n".join(lines), encoding="utf-8")
