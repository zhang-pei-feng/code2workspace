from __future__ import annotations

import json
from pathlib import Path

from experiments.harness.complex_qa_harness.core import (
    SplitScore,
    load_experiment,
    repo_root,
)
from experiments.harness.complex_qa_harness.runner import (
    run_experiment,
    run_baseline,
    should_accept_candidate,
)


def write_config(
    tmp_path: Path,
    *,
    surface_relpath: str,
    proposer_command: list[str] | None = None,
) -> Path:
    prompt = tmp_path / "planning-guide.md"
    output_root = tmp_path / "output"
    batch_file = (
        Path(__file__).resolve().parents[2]
        / "skill_tests"
        / "batches"
        / "complex-qa-suite-v1.md"
    )
    prompt.write_text("planning surface\n", encoding="utf-8")
    proposer_block = ""
    if proposer_command is not None:
        proposer_block = (
            "\n[proposer]\n"
            f"command = {json.dumps(proposer_command)}\n"
            "max_runtime_minutes = 1\n"
        )
    config = tmp_path / "complex_qa.toml"
    config.write_text(
        f"""
[experiment]
name = "complex-qa-harness"
batch_file = "{batch_file}"
output_root = "{output_root}"
max_iterations = 2
{proposer_block}
[surfaces.planning_skill]
kind = "workspace_file"
target = "{surface_relpath}"
filename = "{Path(surface_relpath).name}"
base_file = "{prompt}"

[[cases]]
case_name = "complex-qa-01-may-mainland-dominant-lineage"
split = "train"
weight = 2.0

[[cases]]
case_name = "complex-qa-12-xfg11-risk-assessment-report"
split = "holdout"
weight = 1.0
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def test_load_experiment_reads_case_weights_and_surfaces(tmp_path: Path) -> None:
    surface_relpath = f".code2workspace/skills/{tmp_path.name}-planning-surface.md"
    config = write_config(tmp_path, surface_relpath=surface_relpath)

    experiment = load_experiment(config)

    assert experiment.name == "complex-qa-harness"
    assert experiment.max_iterations == 2
    assert experiment.cases[0].case_name == "complex-qa-01-may-mainland-dominant-lineage"
    assert experiment.cases[0].weight == 2.0
    assert experiment.cases[0].live_eval_case.name == "complex-qa-01-may-mainland-dominant-lineage"
    assert experiment.surfaces["planning_skill"].base_value == "planning surface\n"


def test_should_accept_candidate_prefers_higher_combined_score() -> None:
    baseline_train = SplitScore(
        split="train",
        variant="baseline",
        mean_score=70.0,
        total_weight=2.0,
        outcomes=(),
    )
    baseline_holdout = SplitScore(
        split="holdout",
        variant="baseline",
        mean_score=68.0,
        total_weight=1.0,
        outcomes=(),
    )
    candidate_train = SplitScore(
        split="train",
        variant="candidate",
        mean_score=74.0,
        total_weight=2.0,
        outcomes=(),
    )
    candidate_holdout = SplitScore(
        split="holdout",
        variant="candidate",
        mean_score=69.0,
        total_weight=1.0,
        outcomes=(),
    )

    assert should_accept_candidate(
        baseline_train=baseline_train,
        baseline_holdout=baseline_holdout,
        candidate_train=candidate_train,
        candidate_holdout=candidate_holdout,
    ) is True


def test_run_baseline_writes_split_results(tmp_path: Path, monkeypatch) -> None:
    surface_relpath = f".code2workspace/skills/{tmp_path.name}-planning-surface.md"
    config = write_config(tmp_path, surface_relpath=surface_relpath)
    experiment = load_experiment(config)

    def fake_evaluate_case(*, case, split_dir, run_date):  # noqa: ANN001
        from experiments.harness.complex_qa_harness.core import CaseScoreResult

        case_dir = split_dir / "results" / case.case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        return CaseScoreResult(
            case_name=case.case_name,
            split=case.split,
            weight=case.weight,
            status="passed",
            overall_score=81.0,
            rule_score=20.0,
            judge_score=61.0,
            answer_path=str(case_dir / "answer.txt"),
            trace_path=str(case_dir / "trace.json"),
            judge_path=str(case_dir / "judge.json"),
            log_path=str(case_dir / "run.log"),
        )

    monkeypatch.setattr(
        "experiments.harness.complex_qa_harness.runner.evaluate_case",
        fake_evaluate_case,
    )

    run_root = run_baseline(experiment=experiment, split="train")

    assert run_root.joinpath("variants", "baseline.json").exists()
    assert run_root.joinpath("history", "visible", "train", "baseline", "result.json").exists()


def test_run_experiment_materializes_candidate_and_accepts_improvement(
    tmp_path: Path, monkeypatch
) -> None:
    surface_relpath = f".code2workspace/skills/{tmp_path.name}-planning-surface.md"
    proposer = tmp_path / "proposer.py"
    proposer.write_text(
        f"""
from __future__ import annotations

import os
from pathlib import Path

current = Path(os.environ["CODE2WORKSPACE_HARNESS_CURRENT"])
proposal = Path(os.environ["CODE2WORKSPACE_HARNESS_PROPOSAL"])
(current / "{Path(surface_relpath).name}").write_text("improved planning surface\\n", encoding="utf-8")
proposal.write_text("# Proposal\\n\\n- Summary: improve visible QA scores\\n", encoding="utf-8")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = write_config(
        tmp_path,
        surface_relpath=surface_relpath,
        proposer_command=["python3", str(proposer)],
    )
    experiment = load_experiment(config)
    surface_target = repo_root() / surface_relpath
    surface_target.parent.mkdir(parents=True, exist_ok=True)
    original = surface_target.read_text(encoding="utf-8") if surface_target.exists() else None

    def fake_evaluate_case(*, case, split_dir, run_date):  # noqa: ANN001
        from experiments.harness.complex_qa_harness.core import CaseScoreResult

        current_prompt = surface_target.read_text(encoding="utf-8")
        score = 81.0 if current_prompt == "improved planning surface\n" else 70.0
        case_dir = split_dir / "results" / case.case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        return CaseScoreResult(
            case_name=case.case_name,
            split=case.split,
            weight=case.weight,
            status="passed",
            overall_score=score,
            rule_score=20.0,
            judge_score=score - 20.0,
            answer_path=str(case_dir / "answer.txt"),
            trace_path=str(case_dir / "trace.json"),
            judge_path=str(case_dir / "judge.json"),
            log_path=str(case_dir / "run.log"),
        )

    monkeypatch.setattr(
        "experiments.harness.complex_qa_harness.runner.evaluate_case",
        fake_evaluate_case,
    )

    try:
        report = run_experiment(experiment=experiment, max_iterations=1)
    finally:
        if original is None:
            if surface_target.exists():
                surface_target.unlink()
        else:
            surface_target.write_text(original, encoding="utf-8")

    assert report.final.key == "iter-001"
    assert report.final_train.mean_score == 81.0
    assert report.final_holdout.mean_score == 81.0
