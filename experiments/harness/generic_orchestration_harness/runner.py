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

from code2workspace_cli.generic_experience_store import (
    build_experience_record,
    experience_skill_root,
    rebuild_distilled_guidance,
    write_record,
)
from code2workspace_cli.supervisor_evaluation import write_evaluation_for_run

from experiments.harness.generic_orchestration_harness.core import (
    CandidateEvaluation,
    CaseScoreResult,
    Experiment,
    IterationRecord,
    Proposal,
    RunLayout,
    RunReport,
    SplitScore,
    Variant,
    load_experiment,
    repo_root,
)


SCORE_WEIGHTS = {
    "routing_score": 0.10,
    "graph_fit_score": 0.20,
    "traceability_score": 0.20,
    "evidence_score": 0.20,
    "answer_score": 0.15,
    "efficiency_score": 0.15,
}
EXPERIENCE_EXPORT_MIN_SCORE = 70.0


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
    command = [
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
    ]
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=case_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=case.max_runtime_minutes * 60,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = _timeout_output_to_text(exc.stdout)
        stderr = _timeout_output_to_text(exc.stderr)
        if stderr:
            stderr += "\n"
        stderr += f"Timed out after {case.max_runtime_minutes} minutes."
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")

    run_dir = locate_latest_run_dir(
        case_dir,
        known_run_dirs=known_run_dirs,
        expected_task=case.prompt,
    )
    if run_dir is None:
        return _failed_case_result(
            case=case,
            status="failed",
            returncode=returncode,
            completion_status="timeout" if timed_out else "missing_artifacts",
            completion_level="D0.no_orchestration_run",
            finding=f"no orchestration run directory found for case {case.case_id}",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    if not (run_dir / "generic_trace_summary.json").exists():
        write_evaluation_for_run(run_dir)
    summary_path = run_dir / "generic_trace_summary.json"
    evaluation_path = run_dir / "evaluation.json"
    if not summary_path.exists():
        return _failed_case_result(
            case=case,
            status="failed",
            returncode=returncode,
            completion_status="timeout" if timed_out else "missing_artifacts",
            completion_level="D0.missing_generic_trace_summary",
            finding=f"generic_trace_summary.json missing for run {run_dir}",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            run_dir=run_dir,
            evaluation_path=evaluation_path,
        )
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
        status="failed" if timed_out or returncode != 0 else "passed",
        returncode=returncode,
        completion_status=str(summary.get("completion_status", "")),
        completion_level=str(summary.get("completion_level", "")),
        overall_score=overall_score,
        component_scores=scores,
        findings=(
            (f"case timed out after {case.max_runtime_minutes} minutes.",)
            if timed_out
            else ()
        )
        + findings,
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


def locate_latest_run_dir(
    case_dir: Path,
    *,
    known_run_dirs: set[Path] | None = None,
    expected_task: str | None = None,
) -> Path | None:
    candidates = discover_run_dirs(case_dir)
    if known_run_dirs:
        fresh = [path for path in candidates if path not in known_run_dirs]
        if not fresh:
            return None
        candidates = fresh
    if expected_task:
        matching = [
            path
            for path in candidates
            if _run_dir_request_task(path) == expected_task
        ]
        if matching:
            return matching[-1]
        if any(_run_dir_request_task(path) is not None for path in candidates):
            return None
    return candidates[-1] if candidates else None


def _run_dir_request_task(run_dir: Path) -> str | None:
    request_path = run_dir / "request.json"
    if not request_path.exists():
        return None
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    task = payload.get("task")
    return task if isinstance(task, str) else None


def _timeout_output_to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _failed_case_result(
    *,
    case,
    status: str,
    returncode: int,
    completion_status: str,
    completion_level: str,
    finding: str,
    stdout_path: Path,
    stderr_path: Path,
    run_dir: Path | None = None,
    evaluation_path: Path | None = None,
) -> CaseScoreResult:
    return CaseScoreResult(
        case_id=case.case_id,
        split=case.split,
        weight=case.weight,
        status=status,
        returncode=returncode,
        completion_status=completion_status,
        completion_level=completion_level,
        overall_score=0.0,
        component_scores={},
        findings=(finding,),
        run_dir=str(run_dir or ""),
        generic_trace_summary_path="",
        evaluation_path=str(evaluation_path or ""),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


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


def build_experience_variant(label: str) -> Variant:
    return Variant(label=label, changed_surfaces=(), values={})


def snapshot_experience_skill(*, layout: RunLayout, iteration: int) -> Path | None:
    source = experience_skill_root(repo_root())
    target = layout.iteration_dir(iteration) / "generic_experience_snapshot"
    if target.exists():
        shutil.rmtree(target)
    if not source.exists():
        return None
    shutil.copytree(source, target)
    return target


def restore_experience_skill_snapshot(snapshot: Path | None) -> None:
    target = experience_skill_root(repo_root())
    if target.exists():
        shutil.rmtree(target)
    if snapshot is not None and snapshot.exists():
        shutil.copytree(snapshot, target)


def run_split(*, experiment: Experiment, layout: RunLayout, split: str, variant) -> SplitScore:
    split_dir = layout.split_dir(split=split, variant=variant.key)
    split_dir.mkdir(parents=True, exist_ok=True)
    variant.save(layout.variant_path(variant.key))

    cases = experiment.cases_for_split(split)
    outcomes: list[CaseScoreResult] = []
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


def _export_accepted_candidate_experience(
    *,
    experiment: Experiment,
    layout: RunLayout,
    candidate: CandidateEvaluation,
    previous_train: SplitScore,
    previous_holdout: SplitScore,
) -> list[Path]:
    case_lookup = {case.case_id: case for case in experiment.cases}
    split_baselines = {
        "train": previous_train.mean_score,
    }
    split_candidates = {
        "train": candidate.train.mean_score,
    }
    written: list[Path] = []
    for outcome in candidate.train.outcomes:
        case = case_lookup.get(outcome.case_id)
        if case is None:
            continue
        summary_path = Path(outcome.generic_trace_summary_path)
        run_dir = Path(outcome.run_dir)
        if not summary_path.exists() or not run_dir.exists():
            continue
        generic_trace_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        record = build_experience_record(
            case_id=case.case_id,
            prompt=case.prompt,
            split=case.split,
            variant=candidate.variant,
            harness_run_root=layout.run_root,
            orchestration_run_dir=run_dir,
            generic_trace_summary=generic_trace_summary,
            baseline_split_mean_score=split_baselines.get(case.split, 0.0),
            candidate_split_mean_score=split_candidates.get(case.split, 0.0),
        )
        written.append(write_record(record))
    rebuild_distilled_guidance()
    return written


def _export_training_experience_candidate(
    *,
    experiment: Experiment,
    layout: RunLayout,
    iteration: int,
    current_train: SplitScore,
    reference_train: SplitScore,
) -> list[Path]:
    case_lookup = {case.case_id: case for case in experiment.cases}
    variant = f"iter-{iteration:03d}"
    written: list[Path] = []
    for outcome in current_train.outcomes:
        if not _is_exportable_experience_outcome(outcome):
            continue
        case = case_lookup.get(outcome.case_id)
        if case is None:
            continue
        summary_path = Path(outcome.generic_trace_summary_path)
        run_dir = Path(outcome.run_dir)
        generic_trace_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        record = build_experience_record(
            case_id=case.case_id,
            prompt=case.prompt,
            split=case.split,
            variant=variant,
            harness_run_root=layout.run_root,
            orchestration_run_dir=run_dir,
            generic_trace_summary=generic_trace_summary,
            baseline_split_mean_score=reference_train.mean_score,
            candidate_split_mean_score=current_train.mean_score,
        )
        written.append(write_record(record))
    if written:
        rebuild_distilled_guidance()
    _write_experience_candidate_artifact(
        layout=layout,
        iteration=iteration,
        current_train=current_train,
        reference_train=reference_train,
        written=written,
    )
    return written


def _is_exportable_experience_outcome(outcome: CaseScoreResult) -> bool:
    if outcome.status != "passed" or outcome.returncode != 0:
        return False
    if outcome.completion_status != "completed":
        return False
    if outcome.overall_score < EXPERIENCE_EXPORT_MIN_SCORE:
        return False
    return Path(outcome.generic_trace_summary_path).exists() and Path(outcome.run_dir).exists()


def _write_experience_candidate_artifact(
    *,
    layout: RunLayout,
    iteration: int,
    current_train: SplitScore,
    reference_train: SplitScore,
    written: list[Path],
) -> None:
    iteration_dir = layout.iteration_dir(iteration)
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "experience_candidate.json").write_text(
        json.dumps(
            {
                "iteration": iteration,
                "variant": f"iter-{iteration:03d}",
                "source_split": "train",
                "source_variant": current_train.variant,
                "source_train_mean_score": current_train.mean_score,
                "reference_train_mean_score": reference_train.mean_score,
                "record_count": len(written),
                "record_paths": [str(path) for path in written],
                "target": ".code2workspace/skills/orchestration/generic-experience",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def sync_experience_skill_from_run_root(run_root: Path) -> list[Path]:
    manifest_path = run_root / "manifest.json"
    report_path = run_root / "report.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest.json under {run_root}")
    if not report_path.exists():
        raise FileNotFoundError(f"missing report.json under {run_root}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    case_lookup = {
        str(item["case_id"]): item
        for item in manifest.get("cases", [])
        if isinstance(item, dict) and item.get("case_id")
    }
    previous_train = float(report.get("baseline_train", {}).get("mean_score", 0.0))
    written: list[Path] = []
    for iteration in report.get("iterations", []):
        if not isinstance(iteration, dict):
            continue
        candidate = iteration.get("candidate")
        if not isinstance(candidate, dict) or not candidate.get("accepted"):
            continue
        variant = str(candidate.get("variant", "candidate"))
        train = dict(candidate.get("train") or {})
        current_train = float(train.get("mean_score", previous_train))
        for outcome in train.get("outcomes", []):
            if not isinstance(outcome, dict):
                continue
            case_id = str(outcome.get("case_id", ""))
            case = case_lookup.get(case_id)
            if not isinstance(case, dict):
                continue
            summary_path = Path(str(outcome.get("generic_trace_summary_path", "")))
            orchestration_run_dir = Path(str(outcome.get("run_dir", "")))
            if not summary_path.exists() or not orchestration_run_dir.exists():
                continue
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            record = build_experience_record(
                case_id=case_id,
                prompt=str(case.get("prompt", "")),
                split="train",
                variant=variant,
                harness_run_root=run_root,
                orchestration_run_dir=orchestration_run_dir,
                generic_trace_summary=summary_payload,
                baseline_split_mean_score=previous_train,
                candidate_split_mean_score=current_train,
                created_at=str(report.get("created_at", "")) or None,
            )
            written.append(write_record(record))
        previous_train = current_train
    rebuild_distilled_guidance()
    return written


def run_baseline(*, experiment: Experiment, split: str | None = None, output_root: Path | None = None) -> Path:
    layout = RunLayout(
        output_root=output_root or experiment.output_root,
        experiment_name=experiment.name,
    )
    layout.write_manifest(experiment)
    baseline = build_experience_variant("baseline")
    baseline.save(layout.variant_path(baseline.key))
    splits = (
        [split]
        if split is not None
        else [name for name in ("train", "holdout", "scorecard") if experiment.has_split(name)]
    )
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

    layout = RunLayout(
        output_root=output_root or experiment.output_root,
        experiment_name=experiment.name,
    )
    layout.write_manifest(experiment)

    baseline = build_experience_variant("baseline")
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
        snapshot = snapshot_experience_skill(layout=layout, iteration=index)
        written_records = _export_training_experience_candidate(
            experiment=experiment,
            layout=layout,
            iteration=index,
            current_train=current_train,
            reference_train=baseline_train,
        )
        proposal = Proposal(
            changed_surfaces=(),
            workspace_dir=str(layout.iteration_dir(index)),
            summary=(
                f"Seeded generic-experience with {len(written_records)} train records "
                "and rebuilt distilled guidance."
            ),
        )
        if not written_records:
            restore_experience_skill_snapshot(snapshot)
            iterations.append(
                IterationRecord(
                    iteration=index,
                    starting_variant=current.key,
                    candidate=None,
                )
            )
            break
        candidate_variant = build_experience_variant(f"iter-{index:03d}")

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
            "generic-experience candidate improved combined score without degrading holdout traceability"
            if accepted
            else "generic-experience candidate did not improve combined score enough under holdout guardrails"
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
        else:
            restore_experience_skill_snapshot(snapshot)

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

    sync_skill = subparsers.add_parser(
        "sync-skill",
        help="Backfill generic experience skill records from a completed harness run root",
    )
    sync_skill.add_argument("run_root", type=Path)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "sync-skill":
        written = sync_experience_skill_from_run_root(args.run_root)
        print(len(written))
        return
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
