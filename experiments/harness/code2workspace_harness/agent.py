"""Proposer workspace helpers for the local harness."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import (
    Experiment,
    Proposal,
    RunLayout,
    SplitResult,
    Variant,
    repo_root,
    safe_slug,
)
from .patching import build_variant

DEFAULT_SYSTEM_PROMPT = """You are Better Agent, an outer-loop Deep Agent that improves the code2workspace one-shot harness.

Your job is to read the visible harness feedback and edit the provided surface files so the next eval run passes more repositories.

Rules:
- Edit only files under /current.
- Do not edit train_cases, history, or bookkeeping files except /proposal.md.
- Prefer general harness fixes over repository-specific hacks.
- Do not overfit to the visible train examples. Infer the broader policy or failure mode they expose and encode that policy in the harness surfaces.
- The files under /current are the real harness surfaces. Edit them as final prompt text, rubric text, or other runtime content that the one-shot runner will load.
- Use surface_manifest.json and task.md to understand what each editable file controls.
- Use the visible train failures and copied run artifacts to decide what to change.
- Keep changes concise and coherent.
- Make the smallest set of edits needed for this iteration.
- Stop as soon as /current and /proposal.md are updated.
- When done, write a short explanation to /proposal.md."""


@dataclass(frozen=True)
class ProposerWorkspace:
    """Materialized workspace for one proposer iteration."""

    root: Path
    current_dir: Path
    proposal_file: Path
    surface_files: dict[str, Path]


def build_proposer_workspace(
    *,
    experiment: Experiment,
    current: Variant,
    train_result: SplitResult,
    layout: RunLayout,
    iteration: int,
) -> ProposerWorkspace:
    """Create one proposer workspace from the current accepted variant."""
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
    _write_visible_history(layout=layout, root=root)
    _copy_prior_visible_artifacts(layout=layout, root=root, iteration=iteration)
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
    """Load surface values back out of one proposer workspace."""
    values = dict(current.values)
    for name, path in workspace.surface_files.items():
        values[name] = path.read_text(encoding="utf-8")
    return values


def read_proposal_summary(workspace: ProposerWorkspace) -> str:
    """Read the proposer summary if present."""
    if not workspace.proposal_file.exists():
        return ""
    return workspace.proposal_file.read_text(encoding="utf-8").strip()


def propose_variant(
    *,
    experiment: Experiment,
    current: Variant,
    train_result: SplitResult,
    layout: RunLayout,
    iteration: int,
) -> tuple[Proposal, Variant]:
    """Run one proposer iteration and materialize the resulting candidate variant."""
    workspace = build_proposer_workspace(
        experiment=experiment,
        current=current,
        train_result=train_result,
        layout=layout,
        iteration=iteration,
    )
    _invoke_proposer(experiment=experiment, workspace=workspace)
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


def _invoke_proposer(*, experiment: Experiment, workspace: ProposerWorkspace) -> None:
    """Run the configured proposer inside one workspace."""
    if experiment.proposer_command is not None:
        _invoke_command_proposer(experiment=experiment, workspace=workspace)
        return
    if experiment.better_agent_model is not None:
        invoke_deepagents_proposer(experiment=experiment, workspace=workspace)
        return
    raise ValueError("optimize requires either [proposer].command or [better_agent]")


def _invoke_command_proposer(*, experiment: Experiment, workspace: ProposerWorkspace) -> None:
    """Run the configured proposer command inside one workspace."""
    request = {
        "argv": list(experiment.proposer_command),
        "cwd": str(workspace.root),
        "timeout_seconds": experiment.proposer_max_runtime_minutes * 60,
    }
    (workspace.root / "proposer_request.json").write_text(
        json.dumps(request, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CODE2WORKSPACE_HARNESS_WORKSPACE"] = str(workspace.root.resolve())
    env["CODE2WORKSPACE_HARNESS_CURRENT"] = str(workspace.current_dir.resolve())
    env["CODE2WORKSPACE_HARNESS_PROPOSAL"] = str(workspace.proposal_file.resolve())
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root()), env["PYTHONPATH"]]
        if env.get("PYTHONPATH")
        else [str(repo_root())]
    )
    try:
        completed = subprocess.run(
            experiment.proposer_command,
            cwd=workspace.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=experiment.proposer_max_runtime_minutes * 60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        (workspace.root / "proposer_stdout.log").write_text(exc.stdout or "", encoding="utf-8")
        (workspace.root / "proposer_stderr.log").write_text(exc.stderr or "", encoding="utf-8")
        msg = f"proposer timed out after {experiment.proposer_max_runtime_minutes} minutes"
        raise RuntimeError(msg) from exc

    (workspace.root / "proposer_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (workspace.root / "proposer_stderr.log").write_text(completed.stderr, encoding="utf-8")
    response = {
        "returncode": completed.returncode,
        "command": list(experiment.proposer_command),
    }
    (workspace.root / "proposer_result.json").write_text(
        json.dumps(response, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        msg = f"proposer command failed with exit code {completed.returncode}"
        raise RuntimeError(msg)


def invoke_deepagents_proposer(*, experiment: Experiment, workspace: ProposerWorkspace) -> None:
    """Run the outer Deep Agent against one proposer workspace."""
    request = {
        "workspace_root": str(workspace.root),
        "model": experiment.better_agent_model,
        "max_turns": experiment.better_agent_max_turns,
        "system_prompt": _compose_system_prompt(experiment),
        "deepagents_root": None
        if experiment.better_agent_deepagents_root is None
        else str(experiment.better_agent_deepagents_root),
    }
    (workspace.root / "outer_agent_request.json").write_text(
        json.dumps(request, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = None
    try:
        with _deepagents_import_context(experiment.better_agent_deepagents_root):
            try:
                deepagents_module = importlib.import_module("deepagents")
                backends_module = importlib.import_module("deepagents.backends")
                messages_module = importlib.import_module("langchain_core.messages")
            except ImportError as exc:  # pragma: no cover - depends on local runtime
                msg = (
                    "Could not import deepagents. Install the package in the harness runtime "
                    "or set [better_agent].deepagents_root / DEEPAGENTS_ROOT to a local checkout."
                )
                raise RuntimeError(msg) from exc

            filesystem_backend_cls = backends_module.FilesystemBackend
            create_deep_agent = deepagents_module.create_deep_agent
            human_message_cls = messages_module.HumanMessage
            backend = filesystem_backend_cls(root_dir=str(workspace.root), virtual_mode=True)
            agent = create_deep_agent(
                model=experiment.better_agent_model,
                system_prompt=_compose_system_prompt(experiment),
                backend=backend,
            )
            for attempt in range(3):
                try:
                    result = agent.invoke(
                        {
                            "messages": [
                                human_message_cls(
                                    content=(
                                        "Read /task.md first. Then inspect the current surface files, visible history, "
                                        "and failing train artifacts, edit only /current, and finish by updating "
                                        "/proposal.md."
                                    )
                                )
                            ]
                        },
                        config={"recursion_limit": experiment.better_agent_max_turns},
                    )
                    break
                except Exception as exc:  # pragma: no cover - depends on model provider
                    if attempt == 2 or not _is_transient_model_error(str(exc)):
                        raise
                    time.sleep(2 * (attempt + 1))
    except Exception as exc:
        (workspace.root / "outer_agent_error.json").write_text(
            json.dumps(
                {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise

    if result is None:  # pragma: no cover - defensive fallback
        raise RuntimeError("outer Deep Agent produced no result")
    final_message = _final_ai_message_text(result)
    (workspace.root / "outer_agent_result.json").write_text(
        json.dumps(
            {
                "final_message": final_message,
                "result": _jsonify(result),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_train_artifacts(*, train_result: SplitResult, root: Path) -> None:
    failures_payload = [
        {
            "case_id": outcome.case_id,
            "repo_url": outcome.repo_url,
            "status": outcome.status,
            "completed": outcome.completed,
            "returncode": outcome.returncode,
            "error_message": outcome.error_message,
            "summary_path": outcome.summary_path,
            "manifest_path": outcome.manifest_path,
        }
        for outcome in train_result.failing_outcomes()
    ]
    (root / "train_failures.json").write_text(
        json.dumps(failures_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "train_summary.json").write_text(
        json.dumps(train_result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    train_cases_dir = root / "train_cases"
    train_cases_dir.mkdir(parents=True, exist_ok=True)
    for outcome in train_result.outcomes:
        case_dir = train_cases_dir / safe_slug(outcome.case_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "case.json").write_text(
            json.dumps(
                {
                    "case_id": outcome.case_id,
                    "repo_url": outcome.repo_url,
                    "status": outcome.status,
                    "completed": outcome.completed,
                    "returncode": outcome.returncode,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        source_run_dir = Path(outcome.run_dir)
        for name in ("summary.json", "manifest.json", "agent.log", "prompt.txt", "clone.log"):
            source = source_run_dir / name
            if source.exists():
                shutil.copy2(source, case_dir / name)


def _write_visible_history(*, layout: RunLayout, root: Path) -> None:
    history_dir = root / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[str] = []
    for decision_path in sorted(layout.visible_iterations_dir.glob("*/decision.json")):
        payload = json.loads(decision_path.read_text(encoding="utf-8"))
        summaries.append(
            f"- Iteration {payload['iteration']}: {payload['decision']} "
            f"(train {payload['train_passed']}/{payload['train_total']}, "
            f"holdout {payload['holdout_passed']}/{payload['holdout_total']})"
        )
    if not summaries:
        summaries.append("- No previous iterations yet.")
    (history_dir / "visible_history.md").write_text(
        "# Visible History\n\n" + "\n".join(summaries) + "\n",
        encoding="utf-8",
    )


def _copy_prior_visible_artifacts(*, layout: RunLayout, root: Path, iteration: int) -> None:
    prior_root = root / "history" / "prior_visible"
    prior_root.mkdir(parents=True, exist_ok=True)

    train_root = layout.visible_root / "train"
    if train_root.exists():
        shutil.copytree(train_root, prior_root / "train", dirs_exist_ok=True)

    iterations_root = prior_root / "iterations"
    iterations_root.mkdir(parents=True, exist_ok=True)
    for decision_path in sorted(layout.visible_iterations_dir.glob("*/decision.json")):
        if decision_path.parent.name == f"{iteration:03d}":
            continue
        target_dir = iterations_root / decision_path.parent.name
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(decision_path, target_dir / decision_path.name)
        markdown_path = decision_path.with_suffix(".md")
        if markdown_path.exists():
            shutil.copy2(markdown_path, target_dir / markdown_path.name)
        proposer_workspace = decision_path.parent / "proposer_workspace"
        if proposer_workspace.exists():
            proposer_target = target_dir / "proposer_workspace"
            proposer_target.mkdir(parents=True, exist_ok=True)
            for name in (
                "outer_agent_error.json",
                "outer_agent_request.json",
                "outer_agent_result.json",
                "proposal.md",
                "proposer_request.json",
                "proposer_result.json",
                "proposer_stderr.log",
                "proposer_stdout.log",
                "result.json",
                "task.md",
            ):
                source = proposer_workspace / name
                if source.exists():
                    shutil.copy2(source, proposer_target / name)


def _write_task_file(
    *,
    experiment: Experiment,
    current: Variant,
    train_result: SplitResult,
    root: Path,
) -> None:
    failing_lines = [
        (
            f"- `{outcome.case_id}`: status=`{outcome.status}`, "
            f"completed=`{outcome.completed}`, returncode=`{outcome.returncode}`"
        )
        for outcome in train_result.failing_outcomes()
    ]
    if not failing_lines:
        failing_lines.append("- No train failures are currently visible.")

    surface_lines = [
        f"- `{name}` -> `{surface.filename}` patches `{surface.target}`"
        for name, surface in experiment.surfaces.items()
    ]
    lines = [
        "# Task",
        "",
        "Improve the visible train results by editing only the harness surfaces under `current/`.",
        "",
        "## Current Variant",
        "",
        f"- Label: `{current.label}`",
        f"- Changed surfaces from baseline: `{', '.join(current.changed_surfaces) or 'none'}`",
        "",
        "## Editable Surfaces",
        "",
        *surface_lines,
        "",
        "## Visible Train Failures",
        "",
        *failing_lines,
        "",
        "## Rules",
        "",
        "- Read `surface_manifest.json`, `train_summary.json`, and `train_failures.json` first.",
        "- Use the copied train artifacts under `train_cases/` and prior visible decisions under `history/`.",
        "- Edit only files under `current/` and finish by updating `proposal.md`.",
        "- Do not edit `train_cases/`, `history/`, or this task file.",
        "- Prefer small, coherent changes that improve the harness generally rather than hardcoding one repository.",
        "- The current completion policy is in the `completion_rubric` surface if that surface is exposed.",
        "",
    ]
    (root / "task.md").write_text("\n".join(lines), encoding="utf-8")


def _compose_system_prompt(experiment: Experiment) -> str:
    if experiment.better_agent_system_prompt:
        return experiment.better_agent_system_prompt.strip() + "\n\n" + DEFAULT_SYSTEM_PROMPT
    return DEFAULT_SYSTEM_PROMPT


def _is_transient_model_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "overloaded",
            "overloaded_error",
            "error code: 529",
            "529 -",
            "rate limit",
            "timeout",
        )
    )


def _final_ai_message_text(result: dict[str, Any]) -> str | None:
    messages = result.get("messages", [])
    for message in reversed(messages):
        if getattr(message, "type", None) == "ai":
            content = getattr(message, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(item) for item in content)
            return None if content is None else str(content)
    return None


def _jsonify(value: Any) -> Any:  # noqa: PLR0911
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonify(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(child) for child in value]
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
        except TypeError:
            dumped = value.model_dump()
        return _jsonify(dumped)
    if hasattr(value, "dict"):
        try:
            return _jsonify(value.dict())
        except TypeError:
            return repr(value)
    if hasattr(value, "type"):
        payload: dict[str, Any] = {"type": value.type}
        for name in (
            "id",
            "name",
            "content",
            "content_blocks",
            "tool_calls",
            "invalid_tool_calls",
            "additional_kwargs",
            "response_metadata",
            "usage_metadata",
        ):
            if hasattr(value, name):
                payload[name] = _jsonify(getattr(value, name))
        return payload
    if hasattr(value, "__dict__"):
        return {
            key: _jsonify(child)
            for key, child in vars(value).items()
            if not key.startswith("_")
        }
    return repr(value)


def _resolve_deepagents_root(root: Path | None) -> Path | None:
    if root is not None:
        return root
    env_root = os.environ.get("DEEPAGENTS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    sibling = repo_root().parent / "deepagents"
    return sibling.resolve() if sibling.exists() else None


@contextmanager
def _deepagents_import_context(root: Path | None) -> Iterator[None]:
    resolved_root = _resolve_deepagents_root(root)
    paths: list[str] = []
    if resolved_root is not None:
        package_root = resolved_root / "libs" / "deepagents"
        paths.append(str(package_root if package_root.exists() else resolved_root))
    previous = list(sys.path)
    if paths:
        sys.path[:0] = paths
    try:
        yield
    finally:
        sys.path[:] = previous
