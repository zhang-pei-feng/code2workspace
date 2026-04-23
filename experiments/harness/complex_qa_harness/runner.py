"""Runner for the score-based complex QA harness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from experiments.skill_tests.judge import judge_results
from experiments.skill_tests.runner import run_case

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from experiments.harness.complex_qa_harness.core import (
    CandidateEvaluation,
    CaseScoreResult,
    Experiment,
    IterationRecord,
    Proposal,
    RunLayout,
    RunReport,
    SplitScore,
    load_experiment,
)
from experiments.harness.complex_qa_harness.patching import (
    build_baseline_variant,
    build_variant,
    workspace_override_context,
)


def evaluate_case(*, case, split_dir: Path, run_date: str) -> CaseScoreResult:
    raw_result = run_case(
        case.live_eval_case,
        run_date=run_date,
        output_root=split_dir / "results",
    )
    judged = judge_results([raw_result], run_date=run_date)[0]
    return CaseScoreResult(
        case_name=case.case_name,
        split=case.split,
        weight=case.weight,
        status=str(raw_result["status"]),
        overall_score=float(judged["overall_score"]),
        rule_score=float(judged["rule_score"]),
        judge_score=float(judged["judge_score"]),
        answer_path=str(raw_result["answer_path"]),
        trace_path=str(raw_result["trace_path"]),
        judge_path=str(judged["judge_path"]),
        log_path=str(raw_result["log_path"]),
    )


def aggregate_split_scores(
    *,
    split: str,
    variant: str,
    outcomes: list[CaseScoreResult],
) -> SplitScore:
    total_weight = sum(item.weight for item in outcomes)
    weighted_total = sum(item.overall_score * item.weight for item in outcomes)
    mean_score = 0.0 if total_weight == 0 else weighted_total / total_weight
    return SplitScore(
        split=split,
        variant=variant,
        mean_score=mean_score,
        total_weight=total_weight,
        outcomes=tuple(outcomes),
    )


def should_accept_candidate(
    *,
    baseline_train: SplitScore,
    baseline_holdout: SplitScore,
    candidate_train: SplitScore,
    candidate_holdout: SplitScore,
) -> bool:
    baseline_combined = baseline_train.mean_score + baseline_holdout.mean_score
    candidate_combined = candidate_train.mean_score + candidate_holdout.mean_score
    if candidate_holdout.mean_score + 1.0 < baseline_holdout.mean_score:
        return False
    return candidate_combined > baseline_combined


def run_split(
    *,
    experiment: Experiment,
    layout: RunLayout,
    split: str,
    variant,
) -> SplitScore:
    split_dir = layout.split_dir(split=split, variant=variant.key)
    split_dir.mkdir(parents=True, exist_ok=True)
    variant.save(layout.variant_path(variant.key))
    outcomes: list[CaseScoreResult] = []
    with workspace_override_context(experiment, variant):
        for case in experiment.cases_for_split(split):
            outcomes.append(evaluate_case(case=case, split_dir=split_dir, run_date=layout.run_id))
    result = aggregate_split_scores(split=split, variant=variant.key, outcomes=outcomes)
    result.save(split_dir / "result.json")
    (split_dir / "summary.json").write_text(
        json.dumps(
            {
                "split": split,
                "variant": variant.key,
                "mean_score": result.mean_score,
                "total_weight": result.total_weight,
                "case_count": len(result.outcomes),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def run_baseline(
    *,
    experiment: Experiment,
    split: str | None = None,
    output_root: Path | None = None,
) -> Path:
    layout = RunLayout(
        output_root=output_root or experiment.output_root,
        experiment_name=experiment.name,
    )
    layout.write_manifest(experiment)
    baseline = build_baseline_variant(experiment)
    baseline.save(layout.variant_path(baseline.key))
    splits = [split] if split is not None else [name for name in ("train", "holdout", "scorecard") if experiment.has_split(name)]
    for current_split in splits:
        run_split(
            experiment=experiment,
            layout=layout,
            split=current_split,
            variant=baseline,
        )
    return layout.run_root


def build_proposer_workspace(
    *,
    experiment: Experiment,
    current,
    train_result: SplitScore,
    layout: RunLayout,
    iteration: int,
) -> tuple[Path, dict[str, Path], Path]:
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

    train_payload = train_result.to_dict()
    (root / "train_summary.json").write_text(
        json.dumps(train_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    train_cases_dir = root / "train_cases"
    train_cases_dir.mkdir(parents=True, exist_ok=True)
    for outcome in train_result.outcomes:
        case_dir = train_cases_dir / outcome.case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "result.json").write_text(
            json.dumps(outcome.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for source_path, target_name in (
            (Path(outcome.answer_path), "answer.txt"),
            (Path(outcome.trace_path), "trace.json"),
            (Path(outcome.judge_path), "judge.json"),
            (Path(outcome.log_path), "run.log"),
        ):
            if source_path.exists():
                shutil.copy2(source_path, case_dir / target_name)

    task_file = root / "task.md"
    task_file.write_text(
        "\n".join(
            [
                "# Task",
                "",
                "Improve the visible train scores by editing only files under `current/`.",
                "",
                "Focus on improving:",
                "- answer accuracy",
                "- answer completeness",
                "- answer reasonableness",
                "- trace rationality",
                "",
                "Read `surface_manifest.json`, `train_summary.json`, and `train_cases/` first.",
                "Edit only `current/` and finish by updating `proposal.md`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    proposal_file = root / "proposal.md"
    proposal_file.write_text(
        "# Proposal\n\n- Summary:\n- Why this should help:\n- Surfaces changed:\n",
        encoding="utf-8",
    )
    return root, surface_files, proposal_file


def read_candidate_values(*, current, surface_files: dict[str, Path]) -> dict[str, str]:
    values = dict(current.values)
    for name, path in surface_files.items():
        values[name] = path.read_text(encoding="utf-8")
    return values


def invoke_proposer(
    *,
    experiment: Experiment,
    workspace_root: Path,
    current_dir: Path,
    proposal_file: Path,
) -> None:
    if experiment.proposer_command is None:
        raise ValueError("optimize requires [proposer].command")
    env = os.environ.copy()
    env["CODE2WORKSPACE_HARNESS_WORKSPACE"] = str(workspace_root.resolve())
    env["CODE2WORKSPACE_HARNESS_CURRENT"] = str(current_dir.resolve())
    env["CODE2WORKSPACE_HARNESS_PROPOSAL"] = str(proposal_file.resolve())
    env["CODE2WORKSPACE_HARNESS_REPO_ROOT"] = str(Path(__file__).resolve().parents[3])
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parents[3]), env["PYTHONPATH"]]
        if env.get("PYTHONPATH")
        else [str(Path(__file__).resolve().parents[3])]
    )
    completed = subprocess.run(
        experiment.proposer_command,
        cwd=workspace_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=experiment.proposer_max_runtime_minutes * 60,
        check=False,
    )
    (workspace_root / "proposer_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (workspace_root / "proposer_stderr.log").write_text(completed.stderr, encoding="utf-8")
    (workspace_root / "proposer_result.json").write_text(
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


def run_experiment(
    *,
    experiment: Experiment,
    output_root: Path | None = None,
    max_iterations: int | None = None,
) -> RunReport:
    if not experiment.has_split("train") or not experiment.has_split("holdout"):
        raise ValueError("optimize requires both train and holdout cases")
    if not experiment.has_proposer():
        raise ValueError("optimize requires [proposer].command")

    layout = RunLayout(
        output_root=output_root or experiment.output_root,
        experiment_name=experiment.name,
    )
    layout.write_manifest(experiment)

    baseline = build_baseline_variant(experiment)
    baseline.save(layout.variant_path(baseline.key))
    baseline_train = run_split(
        experiment=experiment,
        layout=layout,
        split="train",
        variant=baseline,
    )
    baseline_holdout = run_split(
        experiment=experiment,
        layout=layout,
        split="holdout",
        variant=baseline,
    )
    current = baseline
    current_train = baseline_train
    current_holdout = baseline_holdout
    iteration_limit = experiment.max_iterations if max_iterations is None else max_iterations

    iterations: list[IterationRecord] = []
    for index in range(1, iteration_limit + 1):
        workspace_root, surface_files, proposal_file = build_proposer_workspace(
            experiment=experiment,
            current=current,
            train_result=current_train,
            layout=layout,
            iteration=index,
        )
        invoke_proposer(
            experiment=experiment,
            workspace_root=workspace_root,
            current_dir=workspace_root / "current",
            proposal_file=proposal_file,
        )
        values = read_candidate_values(current=current, surface_files=surface_files)
        candidate_variant = build_variant(
            experiment=experiment,
            label=f"iter-{index:03d}",
            values=values,
        )
        changed_surfaces = tuple(
            sorted(name for name in experiment.surfaces if values[name] != current.values[name])
        )
        proposal = Proposal(
            changed_surfaces=changed_surfaces,
            workspace_dir=str(workspace_root),
            summary=proposal_file.read_text(encoding="utf-8").strip(),
        )
        train = run_split(
            experiment=experiment,
            layout=layout,
            split="train",
            variant=candidate_variant,
        )
        holdout = run_split(
            experiment=experiment,
            layout=layout,
            split="holdout",
            variant=candidate_variant,
        )
        accepted = should_accept_candidate(
            baseline_train=current_train,
            baseline_holdout=current_holdout,
            candidate_train=train,
            candidate_holdout=holdout,
        )
        reason = (
            "improved combined train + holdout mean score"
            if accepted
            else "did not improve combined train + holdout mean score"
        )
        candidate = CandidateEvaluation(
            variant=candidate_variant.key,
            proposal=proposal,
            train=train,
            holdout=holdout,
            accepted=accepted,
            reason=reason,
        )
        layout.write_iteration_decision(
            iteration=index,
            starting_variant=current.key,
            candidate=candidate,
        )
        iterations.append(
            IterationRecord(
                iteration=index,
                starting_variant=current.key,
                candidate=candidate,
            )
        )
        if accepted:
            current = candidate_variant
            current_train = train
            current_holdout = holdout

    report = RunReport(
        created_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
        config_path=str(experiment.path),
        run_root=str(layout.run_root),
        proposer_mode=experiment.proposer_mode,
        baseline=baseline,
        final=current,
        baseline_train=baseline_train,
        baseline_holdout=baseline_holdout,
        final_train=current_train,
        final_holdout=current_holdout,
        iterations=tuple(iterations),
    )
    layout.write_report(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a complex QA harness config")
    validate.add_argument("config", type=Path)

    run = subparsers.add_parser("run-baseline", help="Run the baseline variant")
    run.add_argument("config", type=Path)
    run.add_argument("--split", choices=["train", "holdout", "scorecard"], default=None)
    run.add_argument("--output-root", type=Path, default=None)

    optimize = subparsers.add_parser("optimize", help="Run the keep/discard loop")
    optimize.add_argument("config", type=Path)
    optimize.add_argument("--max-iterations", type=int, default=None)
    optimize.add_argument("--output-root", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    experiment = load_experiment(args.config)
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "name": experiment.name,
                    "batch_file": str(experiment.batch_file),
                    "surfaces": sorted(experiment.surfaces),
                    "case_count": len(experiment.cases),
                    "splits": sorted({case.split for case in experiment.cases}),
                    "max_iterations": experiment.max_iterations,
                    "has_proposer": experiment.has_proposer(),
                    "proposer_mode": experiment.proposer_mode,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "run-baseline":
        run_root = run_baseline(
            experiment=experiment,
            split=args.split,
            output_root=args.output_root,
        )
        print(json.dumps({"run_root": str(run_root)}, indent=2))
        return 0
    if args.command == "optimize":
        report = run_experiment(
            experiment=experiment,
            output_root=args.output_root,
            max_iterations=args.max_iterations,
        )
        print(
            json.dumps(
                {
                    "run_root": report.run_root,
                    "final_variant": report.final.key,
                },
                indent=2,
            )
        )
        return 0
    raise ValueError(f"unsupported command {args.command}")
