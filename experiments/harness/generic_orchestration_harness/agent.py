"""Proposer workspace helpers for the generic orchestration harness."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .core import (
    Experiment,
    Proposal,
    RunLayout,
    SplitScore,
    Variant,
    repo_root,
    safe_slug,
)
from .patching import build_variant


class ProposerWorkspace:
    """Materialized workspace for one proposer iteration."""

    def __init__(
        self,
        *,
        root: Path,
        current_dir: Path,
        proposal_file: Path,
        surface_files: dict[str, Path],
    ) -> None:
        self.root = root
        self.current_dir = current_dir
        self.proposal_file = proposal_file
        self.surface_files = surface_files


def build_proposer_workspace(
    *,
    experiment: Experiment,
    current: Variant,
    train_result: SplitScore,
    layout: RunLayout,
    iteration: int,
) -> ProposerWorkspace:
    root = layout.proposer_workspace_dir(iteration)
    if root.exists():
        shutil.rmtree(root)

    current_dir = root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)

    surface_files: dict[str, Path] = {}
    manifest: dict[str, dict[str, str]] = {}
    for name, surface in experiment.surfaces.items():
        surface_path = current_dir / surface.filename
        surface_path.parent.mkdir(parents=True, exist_ok=True)
        surface_path.write_text(current.values[name], encoding="utf-8")
        surface_files[name] = surface_path
        manifest[name] = {
            "kind": surface.kind,
            "target": surface.target,
            "file": str(surface_path.relative_to(root)),
        }

    (root / "surface_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_train_artifacts(train_result=train_result, root=root)
    _write_task_file(experiment=experiment, current=current, train_result=train_result, root=root)

    proposal_file = root / "proposal.md"
    proposal_file.write_text(
        "# Proposal\n\n"
        "- Summary:\n"
        "- Why this should help:\n"
        "- Surfaces changed:\n",
        encoding="utf-8",
    )
    return ProposerWorkspace(
        root=root,
        current_dir=current_dir,
        proposal_file=proposal_file,
        surface_files=surface_files,
    )


def load_candidate_values(*, current: Variant, workspace: ProposerWorkspace) -> dict[str, str]:
    values = dict(current.values)
    for name, path in workspace.surface_files.items():
        values[name] = path.read_text(encoding="utf-8")
    return values


def read_proposal_summary(workspace: ProposerWorkspace) -> str:
    if not workspace.proposal_file.exists():
        return ""
    return workspace.proposal_file.read_text(encoding="utf-8").strip()


def propose_variant(
    *,
    experiment: Experiment,
    current: Variant,
    train_result: SplitScore,
    layout: RunLayout,
    iteration: int,
) -> tuple[Proposal, Variant]:
    workspace = build_proposer_workspace(
        experiment=experiment,
        current=current,
        train_result=train_result,
        layout=layout,
        iteration=iteration,
    )
    invoke_command_proposer(experiment=experiment, workspace=workspace)
    values = load_candidate_values(current=current, workspace=workspace)
    changed_surfaces = tuple(
        sorted(name for name in experiment.surfaces if values[name] != current.values[name])
    )
    proposal = Proposal(
        changed_surfaces=changed_surfaces,
        workspace_dir=str(workspace.root),
        summary=read_proposal_summary(workspace),
    )
    candidate = build_variant(
        experiment=experiment,
        label=f"iter-{iteration:03d}",
        values=values,
    )
    (workspace.root / "result.json").write_text(
        json.dumps(
            {
                "proposal": proposal.to_dict(),
                "candidate_variant": candidate.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return proposal, candidate


def invoke_command_proposer(*, experiment: Experiment, workspace: ProposerWorkspace) -> None:
    if experiment.proposer_command is None:
        raise ValueError("optimize requires [proposer].command")
    env = os.environ.copy()
    env["CODE2WORKSPACE_HARNESS_WORKSPACE"] = str(workspace.root.resolve())
    env["CODE2WORKSPACE_HARNESS_CURRENT"] = str(workspace.current_dir.resolve())
    env["CODE2WORKSPACE_HARNESS_PROPOSAL"] = str(workspace.proposal_file.resolve())
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root()), env["PYTHONPATH"]]
        if env.get("PYTHONPATH")
        else [str(repo_root())]
    )
    completed = subprocess.run(
        experiment.proposer_command,
        cwd=workspace.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=experiment.proposer_max_runtime_minutes * 60,
        check=False,
    )
    (workspace.root / "proposer_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (workspace.root / "proposer_stderr.log").write_text(completed.stderr, encoding="utf-8")
    (workspace.root / "proposer_result.json").write_text(
        json.dumps(
            {
                "returncode": completed.returncode,
                "command": list(experiment.proposer_command),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"proposer command failed with exit code {completed.returncode}")


def _write_train_artifacts(*, train_result: SplitScore, root: Path) -> None:
    (root / "train_summary.json").write_text(
        json.dumps(train_result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    train_cases_dir = root / "train_cases"
    train_cases_dir.mkdir(parents=True, exist_ok=True)
    for outcome in train_result.outcomes:
        case_dir = train_cases_dir / safe_slug(outcome.case_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "result.json").write_text(
            json.dumps(outcome.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for source_path, target_name in (
            (Path(outcome.generic_trace_summary_path), "generic_trace_summary.json"),
            (Path(outcome.evaluation_path), "evaluation.json"),
            (Path(outcome.stdout_path), "stdout.txt"),
            (Path(outcome.stderr_path), "stderr.txt"),
        ):
            if source_path.exists():
                shutil.copy2(source_path, case_dir / target_name)
        source_run_dir = Path(outcome.run_dir)
        for name in ("final_response.md", "final_summary.md"):
            source = source_run_dir / name
            if source.exists():
                shutil.copy2(source, case_dir / name)


def _write_task_file(
    *,
    experiment: Experiment,
    current: Variant,
    train_result: SplitScore,
    root: Path,
) -> None:
    low_components = sorted(
        train_result.component_means.items(),
        key=lambda item: item[1],
    )[:3]
    low_component_lines = [f"- `{name}` mean: `{value:.1f}`" for name, value in low_components]
    if not low_component_lines:
        low_component_lines.append("- No train component scores are available.")

    surface_lines = [
        f"- `{name}` -> `{surface.filename}` patches `{surface.target}`"
        for name, surface in experiment.surfaces.items()
    ]
    lines = [
        "# Task",
        "",
        "Improve the visible generic orchestration train scores by editing only the guidance surfaces under `current/`.",
        "",
        "## Current Variant",
        "",
        f"- Label: `{current.label}`",
        f"- Changed surfaces from baseline: `{', '.join(current.changed_surfaces) or 'none'}`",
        "",
        "## Lowest Train Components",
        "",
        *low_component_lines,
        "",
        "## Editable Surfaces",
        "",
        *surface_lines,
        "",
        "## Rules",
        "",
        "- Read `surface_manifest.json` and `train_summary.json` first.",
        "- Use `train_cases/` artifacts to understand low scores and repeated findings.",
        "- Edit only files under `current/` and finish by updating `proposal.md`.",
        "- Prefer generic orchestration improvements over one-case hacks.",
        "- Keep traceability intact while improving graph fit, evidence use, answer quality, or efficiency.",
        "",
    ]
    (root / "task.md").write_text("\n".join(lines), encoding="utf-8")
