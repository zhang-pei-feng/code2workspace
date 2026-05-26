from __future__ import annotations

from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from experiments.harness.generic_orchestration_harness.core import (
    CaseScoreResult,
    GenericCase,
    SplitScore,
    load_experiment,
)
from experiments.harness.generic_orchestration_harness.runner import (
    aggregate_case_score,
    evaluate_case,
    locate_latest_run_dir,
    run_baseline,
    run_experiment,
    should_accept_candidate,
)


def write_config(tmp_path: Path) -> Path:
    output_root = tmp_path / "output"
    config = tmp_path / "generic_harness.toml"
    config.write_text(
        f"""
[experiment]
name = "generic-harness-demo"
output_root = "{output_root}"
max_iterations = 2
max_parallel_cases = 1

[[cases]]
case_id = "generic-train"
split = "train"
weight = 2.0
max_runtime_minutes = 5
prompt = "train prompt"

[[cases]]
case_id = "generic-holdout"
split = "holdout"
weight = 1.0
max_runtime_minutes = 5
prompt = "holdout prompt"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def _result(
    *,
    case_id: str,
    split: str,
    weight: float,
    overall_score: float,
    traceability: float,
    run_dir: str,
) -> CaseScoreResult:
    return CaseScoreResult(
        case_id=case_id,
        split=split,
        weight=weight,
        status="passed",
        returncode=0,
        completion_status="completed",
        completion_level="D6.evidence_boundary_preserved",
        overall_score=overall_score,
        component_scores={
            "routing_score": 100.0,
            "graph_fit_score": 85.0,
            "traceability_score": traceability,
            "evidence_score": 80.0,
            "answer_score": 80.0,
            "efficiency_score": 90.0,
        },
        findings=("Generic trace is complete enough for harness comparison.",),
        run_dir=run_dir,
        generic_trace_summary_path=run_dir,
        evaluation_path=run_dir,
        stdout_path=run_dir,
        stderr_path=run_dir,
    )


def test_load_experiment_reads_generic_cases_without_editable_surfaces(tmp_path: Path) -> None:
    config = write_config(tmp_path)

    experiment = load_experiment(config)

    assert experiment.name == "generic-harness-demo"
    assert experiment.max_iterations == 2
    assert experiment.cases[0].case_id == "generic-train"
    assert experiment.cases[0].weight == 2.0
    assert experiment.proposer_mode == "experience_memory"


def test_load_experiment_rejects_legacy_editable_surfaces(tmp_path: Path) -> None:
    surface = tmp_path / "surface.md"
    surface.write_text("surface\n", encoding="utf-8")
    config = tmp_path / "legacy_surfaces.toml"
    config.write_text(
        f"""
[experiment]
name = "legacy-surfaces"
output_root = "{tmp_path / 'output'}"

[surfaces.prompt]
kind = "workspace_file"
target = "experiments/harness/surfaces/legacy.md"
base_file = "{surface}"

[[cases]]
case_id = "generic-train"
split = "train"
prompt = "train prompt"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        load_experiment(config)
    except ValueError as exc:
        assert "no longer supports editable surfaces" in str(exc)
    else:
        raise AssertionError("legacy editable surfaces should be rejected")


def test_load_experiment_rejects_legacy_surface_proposer(tmp_path: Path) -> None:
    config = tmp_path / "legacy_proposer.toml"
    config.write_text(
        f"""
[experiment]
name = "legacy-proposer"
output_root = "{tmp_path / 'output'}"

[proposer]
command = ["python3", "experiments/harness/proposers/generic_orchestration_surface_proposer.py"]

[[cases]]
case_id = "generic-train"
split = "train"
prompt = "train prompt"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        load_experiment(config)
    except ValueError as exc:
        assert "no longer supports a surface proposer" in str(exc)
    else:
        raise AssertionError("legacy surface proposer should be rejected")


def test_aggregate_case_score_uses_weighted_components() -> None:
    score = aggregate_case_score(
        {
            "routing_score": 100.0,
            "graph_fit_score": 80.0,
            "traceability_score": 90.0,
            "evidence_score": 70.0,
            "answer_score": 60.0,
            "efficiency_score": 50.0,
        }
    )

    assert score == 74.5


def test_locate_latest_run_dir_prefers_matching_request_task(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    matching = case_dir / "workspace" / "20260525010101" / "orchestration_runs" / "run-a"
    unrelated = case_dir / "workspace" / "20260525010102" / "orchestration_runs" / "run-b"
    matching.mkdir(parents=True)
    unrelated.mkdir(parents=True)
    (matching / "request.json").write_text('{"task": "target prompt"}\n', encoding="utf-8")
    (unrelated / "request.json").write_text('{"task": "other prompt"}\n', encoding="utf-8")

    selected = locate_latest_run_dir(
        case_dir,
        expected_task="target prompt",
    )

    assert selected == matching


def test_locate_latest_run_dir_ignores_fresh_mismatched_request_task(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    known = case_dir / "workspace" / "20260525010101" / "orchestration_runs" / "run-a"
    unrelated = case_dir / "workspace" / "20260525010102" / "orchestration_runs" / "run-b"
    known.mkdir(parents=True)
    unrelated.mkdir(parents=True)
    (known / "request.json").write_text('{"task": "old prompt"}\n', encoding="utf-8")
    (unrelated / "request.json").write_text('{"task": "other prompt"}\n', encoding="utf-8")

    selected = locate_latest_run_dir(
        case_dir,
        known_run_dirs={known},
        expected_task="target prompt",
    )

    assert selected is None


def test_evaluate_case_records_timeout_without_crashing(tmp_path: Path, monkeypatch) -> None:
    case = GenericCase(
        case_id="generic-timeout",
        prompt="target prompt",
        split="holdout",
        weight=1.0,
        max_runtime_minutes=1,
    )

    def fake_run(*_args, **_kwargs):  # noqa: ANN202
        raise subprocess.TimeoutExpired(
            cmd=["code2workspace"],
            timeout=60,
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.subprocess.run",
        fake_run,
    )

    result = evaluate_case(case=case, split_dir=tmp_path / "split")

    assert result.status == "failed"
    assert result.returncode == -1
    assert result.completion_level == "D0.no_orchestration_run"
    assert Path(result.stdout_path).read_text(encoding="utf-8") == "partial stdout"
    assert "Timed out after 1 minutes." in Path(result.stderr_path).read_text(encoding="utf-8")


def test_should_accept_candidate_respects_holdout_traceability_guardrail() -> None:
    baseline_train = SplitScore(
        split="train",
        variant="baseline",
        mean_score=70.0,
        total_weight=1.0,
        component_means={"traceability_score": 100.0},
        outcomes=(),
    )
    baseline_holdout = SplitScore(
        split="holdout",
        variant="baseline",
        mean_score=72.0,
        total_weight=1.0,
        component_means={"traceability_score": 100.0},
        outcomes=(),
    )
    candidate_train = SplitScore(
        split="train",
        variant="candidate",
        mean_score=78.0,
        total_weight=1.0,
        component_means={"traceability_score": 100.0},
        outcomes=(),
    )
    candidate_holdout = SplitScore(
        split="holdout",
        variant="candidate",
        mean_score=80.0,
        total_weight=1.0,
        component_means={"traceability_score": 95.0},
        outcomes=(),
    )

    assert (
        should_accept_candidate(
            baseline_train=baseline_train,
            baseline_holdout=baseline_holdout,
            candidate_train=candidate_train,
            candidate_holdout=candidate_holdout,
        )
        is False
    )


def test_run_baseline_writes_split_results(tmp_path: Path, monkeypatch) -> None:
    config = write_config(tmp_path)
    experiment = load_experiment(config)

    def fake_evaluate_case(*, case, split_dir):  # noqa: ANN001
        case_dir = split_dir / "results" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        return _result(
            case_id=case.case_id,
            split=case.split,
            weight=case.weight,
            overall_score=80.0,
            traceability=100.0,
            run_dir=str(case_dir / "artifact.json"),
        )

    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.evaluate_case",
        fake_evaluate_case,
    )

    run_root = run_baseline(experiment=experiment, split="train")

    assert run_root.joinpath("variants", "baseline.json").exists()
    assert run_root.joinpath("history", "visible", "train", "baseline", "result.json").exists()


def test_run_experiment_accepts_improved_candidate(tmp_path: Path, monkeypatch) -> None:
    config = write_config(tmp_path)
    experiment = load_experiment(config)

    def fake_evaluate_case(*, case, split_dir):  # noqa: ANN001
        score = 82.0 if split_dir.name == "iter-001" else 70.0
        traceability = 100.0
        case_dir = split_dir / "results" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        artifact = case_dir / "artifact.json"
        artifact.write_text("{}", encoding="utf-8")
        return _result(
            case_id=case.case_id,
            split=case.split,
            weight=case.weight,
            overall_score=score,
            traceability=traceability,
            run_dir=str(artifact),
        )

    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.evaluate_case",
        fake_evaluate_case,
    )

    def fake_export_training_experience_candidate(**kwargs):  # noqa: ANN003
        path = kwargs["layout"].iteration_dir(kwargs["iteration"]) / "experience_candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return [path]

    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner._export_training_experience_candidate",
        fake_export_training_experience_candidate,
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.snapshot_experience_skill",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.restore_experience_skill_snapshot",
        lambda _snapshot: None,
    )

    report = run_experiment(experiment=experiment, max_iterations=1)

    assert report.final.key == "iter-001"
    assert report.final_train.mean_score == 82.0
    assert report.final_holdout is not None
    assert report.final_holdout.mean_score == 82.0


def test_run_experiment_restores_experience_snapshot_on_rejection(tmp_path: Path, monkeypatch) -> None:
    config = write_config(tmp_path)
    experiment = load_experiment(config)
    restored: list[Path | None] = []

    def fake_evaluate_case(*, case, split_dir):  # noqa: ANN001
        score = 68.0 if split_dir.name == "iter-001" else 70.0
        case_dir = split_dir / "results" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        artifact = case_dir / "artifact.json"
        artifact.write_text("{}", encoding="utf-8")
        return _result(
            case_id=case.case_id,
            split=case.split,
            weight=case.weight,
            overall_score=score,
            traceability=100.0,
            run_dir=str(artifact),
        )

    def fake_export_training_experience_candidate(**kwargs):  # noqa: ANN003
        path = kwargs["layout"].iteration_dir(kwargs["iteration"]) / "experience_candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return [path]

    snapshot = tmp_path / "snapshot"
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.evaluate_case",
        fake_evaluate_case,
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner._export_training_experience_candidate",
        fake_export_training_experience_candidate,
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.snapshot_experience_skill",
        lambda **_kwargs: snapshot,
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.restore_experience_skill_snapshot",
        lambda item: restored.append(item),
    )

    report = run_experiment(experiment=experiment, max_iterations=1)

    assert report.final.key == "baseline"
    assert report.iterations[0].candidate is not None
    assert report.iterations[0].candidate.accepted is False
    assert restored == [snapshot]
