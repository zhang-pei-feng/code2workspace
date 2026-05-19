"""Runner for the generic orchestration harness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from code2workspace_cli.supervisor_evaluation import write_evaluation_for_run

from experiments.harness.generic_orchestration_harness.agent import propose_variant
from experiments.harness.generic_orchestration_harness.core import (
    CandidateEvaluation,
    CaseScoreResult,
    Experiment,
    IterationRecord,
    RunLayout,
    RunReport,
    SplitScore,
    load_experiment,
    repo_root,
)
from experiments.harness.generic_orchestration_harness.patching import (
    build_baseline_variant,
    workspace_override_context,
)


SCORE_WEIGHTS = {
    "routing_score": 0.10,
    "graph_fit_score": 0.20,
    "traceability_score": 0.20,
    "evidence_score": 0.20,
    "answer_score": 0.15,
    "efficiency_score": 0.15,
}


def evaluate_case(*, case, split_dir: Path) -> CaseScoreResult:
    case_dir = split_dir / "results" / case.case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    known_run_dirs = set(discover_run_dirs(case_dir))

    prompt_path = case_dir / "prompt.txt"
    prompt_path.write_text(case.prompt, encoding="utf-8")
    stdout_path = case_dir / "stdout.txt"
    stderr_path = case_dir / "stderr.txt"

    env = os.environ.copy()
    env["CODE2WORKSPACE_CLI_DISABLE_UPDATE_CHECK"] = "1"
    env["CODE2WORKSPACE_SUPERVISOR_RAW_WORKER_TRACE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root()), env["PYTHONPATH"]]
        if env.get("PYTHONPATH")
        else [str(repo_root())]
    )
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root() / "libs" / "cli"),
            "code2workspace",
            "--session-workdir-mode",
            "isolated",
            "--no-mcp",
            "-n",
            case.prompt,
            "-q",
        ],
        cwd=case_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=case.max_runtime_minutes * 60,
        check=False,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    run_dir = locate_latest_run_dir(case_dir, known_run_dirs=known_run_dirs)
    if run_dir is None:
        raise RuntimeError(f"no orchestration run directory found for case {case.case_id}")

    if not (run_dir / "generic_trace_summary.json").exists():
        write_evaluation_for_run(run_dir)
    summary_path = run_dir / "generic_trace_summary.json"
    evaluation_path = run_dir / "evaluation.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scores = {
        str(name): float(value)
        for name, value in summary.get("scores", {}).items()
        if isinstance(value, int | float)
    }
    overall_score = aggregate_case_score(scores)
    findings = tuple(str(item) for item in summary.get("findings", []) if isinstance(item, str))
    return CaseScoreResult(
        case_id=case.case_id,
        split=case.split,
        weight=case.weight,
        status="passed" if completed.returncode == 0 else "failed",
        returncode=completed.returncode,
        completion_status=str(summary.get("completion_status", "")),
        completion_level=str(summary.get("completion_level", "")),
        overall_score=overall_score,
        component_scores=scores,
        findings=findings,
        run_dir=str(run_dir),
        generic_trace_summary_path=str(summary_path),
        evaluation_path=str(evaluation_path),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def discover_run_dirs(case_dir: Path) -> list[Path]:
    candidates = set(case_dir.glob("workspace/*/orchestration_runs/*"))
    candidates.update((repo_root() / "workspace").glob("*/orchestration_runs/*"))
    return sorted(path for path in candidates if path.is_dir())


def locate_latest_run_dir(case_dir: Path, *, known_run_dirs: set[Path] | None = None) -> Path | None:
    candidates = discover_run_dirs(case_dir)
    if known_run_dirs:
        fresh = [path for path in candidates if path not in known_run_dirs]
        if fresh:
            candidates = fresh
    return candidates[-1] if candidates else None


def aggregate_case_score(scores: dict[str, float]) -> float:
    weighted_total = 0.0
    total_weight = 0.0
    for name, weight in SCORE_WEIGHTS.items():
        if name not in scores:
            continue
        weighted_total += scores[name] * weight
        total_weight += weight
    return 0.0 if total_weight == 0 else round(weighted_total / total_weight, 3)


def aggregate_split_scores(*, split: str, variant: str, outcomes: list[CaseScoreResult]) -> SplitScore:
    total_weight = sum(item.weight for item in outcomes)
    weighted_total = sum(item.overall_score * item.weight for item in outcomes)
    mean_score = 0.0 if total_weight == 0 else weighted_total / total_weight
    component_totals: dict[str, float] = {}
    for outcome in outcomes:
        for name, value in outcome.component_scores.items():
            component_totals[name] = component_totals.get(name, 0.0) + (value * outcome.weight)
    component_means = {
        name: round(total / total_weight, 3)
        for name, total in component_totals.items()
        if total_weight > 0
    }
    return SplitScore(
        split=split,
        variant=variant,
        mean_score=mean_score,
        total_weight=total_weight,
        component_means=component_means,
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
    holdout_trace = candidate_holdout.component_means.get("traceability_score", 0.0)
    baseline_holdout_trace = baseline_holdout.component_means.get("traceability_score", 0.0)
    if holdout_trace + 0.5 < baseline_holdout_trace:
        return False
    if candidate_holdout.mean_score + 1.0 < baseline_holdout.mean_score:
        return False
    return candidate_combined > baseline_combined


def run_split(*, experiment: Experiment, layout: RunLayout, split: str, variant) -> SplitScore:
    split_dir = layout.split_dir(split=split, variant=variant.key)
    split_dir.mkdir(parents=True, exist_ok=True)
    variant.save(layout.variant_path(variant.key))

    cases = experiment.cases_for_split(split)
    outcomes: list[CaseScoreResult] = []
    with workspace_override_context(experiment, variant):
        if experiment.max_parallel_cases <= 1 or len(cases) <= 1:
            for case in cases:
                outcomes.append(evaluate_case(case=case, split_dir=split_dir))
        else:
            indexed: list[CaseScoreResult | None] = [None] * len(cases)
            with ThreadPoolExecutor(max_workers=experiment.max_parallel_cases) as executor:
                future_to_index = {
                    executor.submit(evaluate_case, case=case, split_dir=split_dir): index
                    for index, case in enumerate(cases)
                }
                for future in as_completed(future_to_index):
                    indexed[future_to_index[future]] = future.result()
            outcomes = [item for item in indexed if item is not None]

    result = aggregate_split_scores(split=split, variant=variant.key, outcomes=outcomes)
    result.save(split_dir / "result.json")
    (split_dir / "summary.json").write_text(
        json.dumps(
            {
                "split": split,
                "variant": variant.key,
                "mean_score": result.mean_score,
                "total_weight": result.total_weight,
                "component_means": result.component_means,
                "case_count": len(result.outcomes),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def run_baseline(*, experiment: Experiment, split: str | None = None, output_root: Path | None = None) -> Path:
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
        accepted = should_accept_candidate(
            baseline_train=current_train,
            baseline_holdout=current_holdout,
            candidate_train=train,
            candidate_holdout=holdout,
        )
        reason = (
            "improved combined generic harness score without degrading holdout traceability"
            if accepted
            else "did not improve combined score enough under holdout guardrails"
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

    validate = subparsers.add_parser("validate", help="Validate a generic harness config")
    validate.add_argument("config", type=Path)

    baseline = subparsers.add_parser("baseline", help="Run the baseline variant")
    baseline.add_argument("config", type=Path)
    baseline.add_argument("--split", choices=("train", "holdout", "scorecard"))

    optimize = subparsers.add_parser("optimize", help="Run the keep/discard loop")
    optimize.add_argument("config", type=Path)
    optimize.add_argument("--max-iterations", type=int)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    experiment = load_experiment(args.config)
    if args.command == "validate":
        print(args.config)
        return
    if args.command == "baseline":
        print(run_baseline(experiment=experiment, split=args.split))
        return
    report = run_experiment(
        experiment=experiment,
        max_iterations=args.max_iterations,
    )
    print(report.run_root)


if __name__ == "__main__":
    main()
