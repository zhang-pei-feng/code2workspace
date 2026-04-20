"""Local harness runner for code2workspace one-shot experiments."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from experiments.harness.code2workspace_harness.agent import propose_variant
from experiments.harness.code2workspace_harness.core import (
    CandidateEvaluation,
    CaseResult,
    Experiment,
    IterationRecord,
    RunLayout,
    RunReport,
    SplitResult,
    load_experiment,
)
from experiments.harness.code2workspace_harness.patching import build_baseline_variant, workspace_override_context
from experiments.oneshot.run_repo_task import run_repo_task


def run_case(
    *,
    experiment: Experiment,
    layout: RunLayout,
    split: str,
    variant_label: str,
    case,
) -> CaseResult:
    """Run one repository case through the existing one-shot entrypoint."""
    split_dir = layout.split_dir(split=split, variant=variant_label)
    output_root = split_dir / "results"
    result = run_repo_task(
        case.repo_url,
        workspace_root=experiment.workspace_root,
        output_root=output_root,
        max_runtime_minutes=case.max_runtime_minutes,
    )
    summary_path = Path(str(result["summary_path"]))
    summary_payload = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else {}
    )
    return CaseResult(
        case_id=case.case_id,
        repo_url=case.repo_url,
        split=split,
        status=str(result["status"]),
        completed=bool(result["completed"]),
        returncode=int(result["returncode"]),
        run_dir=str(result["run_dir"]),
        summary_path=str(result["summary_path"]),
        manifest_path=str(result["manifest_path"]),
        error_message=summary_payload.get("error"),
    )


def run_split(
    *,
    experiment: Experiment,
    layout: RunLayout,
    split: str,
    variant,
) -> SplitResult:
    """Run one variant across all cases in one split."""
    split_dir = layout.split_dir(split=split, variant=variant.key)
    split_dir.mkdir(parents=True, exist_ok=True)
    variant.save(layout.variant_path(variant.key))

    outcomes: list[CaseResult] = []
    with workspace_override_context(experiment, variant):
        for case in experiment.cases_for_split(split):
            outcomes.append(
                run_case(
                    experiment=experiment,
                    layout=layout,
                    split=split,
                    variant_label=variant.key,
                    case=case,
                )
            )
    result = SplitResult(
        split=split,
        variant=variant.key,
        passed=sum(1 for item in outcomes if item.passed),
        total=len(outcomes),
        outcomes=tuple(outcomes),
    )
    result.save(split_dir / "result.json")
    (split_dir / "summary.json").write_text(
        json.dumps(
            {
                "split": split,
                "variant": variant.key,
                "passed": result.passed,
                "total": result.total,
                "correctness": result.correctness,
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
    """Run the baseline harness variant across one or more splits."""
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

    summary_path = layout.run_root / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "experiment": experiment.name,
                "run_id": layout.run_id,
                "run_root": str(layout.run_root),
                "variant": baseline.key,
                "splits": splits,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return layout.run_root


def run_experiment(
    *,
    experiment: Experiment,
    output_root: Path | None = None,
    max_iterations: int | None = None,
) -> RunReport:
    """Run the keep/discard optimization loop."""
    if not experiment.has_split("train") or not experiment.has_split("holdout"):
        raise ValueError("optimize requires both train and holdout cases")
    if not experiment.has_proposer():
        raise ValueError("optimize requires either [proposer].command or [better_agent]")

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
        if current_train.passed == current_train.total and current_holdout.passed == current_holdout.total:
            break

        proposal, candidate_variant = propose_variant(
            experiment=experiment,
            current=current,
            train_result=current_train,
            layout=layout,
            iteration=index,
        )
        if not proposal.changed_surfaces:
            iterations.append(
                IterationRecord(
                    iteration=index,
                    starting_variant=current.key,
                    candidate=None,
                )
            )
            break

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
        current_combined = current_train.passed + current_holdout.passed
        candidate_combined = train.passed + holdout.passed
        accepted = candidate_combined > current_combined
        reason = (
            "improved combined train + holdout pass count"
            if accepted
            else "did not improve combined train + holdout pass count"
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

    baseline_scorecard = _run_optional_scorecard(
        experiment=experiment,
        layout=layout,
        variant=baseline,
    )
    final_scorecard = _run_optional_scorecard(
        experiment=experiment,
        layout=layout,
        variant=current,
    )
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
        baseline_scorecard=baseline_scorecard,
        final_scorecard=final_scorecard,
        iterations=tuple(iterations),
    )
    layout.write_report(report)
    return report


def _run_optional_scorecard(
    *,
    experiment: Experiment,
    layout: RunLayout,
    variant,
) -> SplitResult | None:
    if not experiment.has_split("scorecard"):
        return None
    return run_split(
        experiment=experiment,
        layout=layout,
        split="scorecard",
        variant=variant,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a harness config")
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
    """Run the harness CLI."""
    args = parse_args()
    experiment = load_experiment(args.config)
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "name": experiment.name,
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
                    "final_changed_surfaces": list(report.final.changed_surfaces),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
