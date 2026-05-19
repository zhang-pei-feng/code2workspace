from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from experiments.harness.generic_orchestration_harness.core import (
    CaseScoreResult,
    SplitScore,
    load_experiment,
    repo_root,
)
from experiments.harness.generic_orchestration_harness.patching import (
    build_baseline_variant,
    workspace_override_context,
)
from experiments.harness.generic_orchestration_harness.runner import (
    aggregate_case_score,
    aggregate_split_scores,
    run_baseline,
    run_experiment,
    should_accept_candidate,
)


def write_config(
    tmp_path: Path,
    *,
    surface_relpath: str,
    proposer_command: list[str] | None = None,
) -> Path:
    surface = tmp_path / "surface.md"
    output_root = tmp_path / "output"
    surface.write_text("surface\n", encoding="utf-8")
    proposer_block = ""
    if proposer_command is not None:
        proposer_block = (
            "\n[proposer]\n"
            f"command = {json.dumps(proposer_command)}\n"
            "max_runtime_minutes = 1\n"
        )
    config = tmp_path / "generic_harness.toml"
    config.write_text(
        f"""
[experiment]
name = "generic-harness-demo"
output_root = "{output_root}"
max_iterations = 2
max_parallel_cases = 1
{proposer_block}
[surfaces.prompt]
kind = "workspace_file"
target = "{surface_relpath}"
filename = "{Path(surface_relpath).name}"
base_file = "{surface}"

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


def test_load_experiment_reads_generic_cases_and_surfaces(tmp_path: Path) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_surface.md"
    config = write_config(tmp_path, surface_relpath=surface_relpath)

    experiment = load_experiment(config)

    assert experiment.name == "generic-harness-demo"
    assert experiment.max_iterations == 2
    assert experiment.cases[0].case_id == "generic-train"
    assert experiment.cases[0].weight == 2.0
    assert experiment.surfaces["prompt"].base_value == "surface\n"


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


def test_workspace_override_context_restores_surface_file(tmp_path: Path) -> None:
    target = repo_root() / "experiments/harness/surfaces" / f"{tmp_path.name}_override.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("before\n", encoding="utf-8")
    config = tmp_path / "override.toml"
    config.write_text(
        f"""
[experiment]
name = "override-demo"
output_root = "{tmp_path / 'output'}"

[surfaces.prompt]
kind = "workspace_file"
target = "{target.relative_to(repo_root())}"
filename = "{target.name}"
base_value = "before\\n"

[[cases]]
case_id = "generic-train"
split = "train"
prompt = "train prompt"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    experiment = load_experiment(config)
    variant = build_baseline_variant(experiment)
    variant = type(variant)(
        label=variant.label,
        changed_surfaces=("prompt",),
        values={"prompt": "after\n"},
    )

    try:
        with workspace_override_context(experiment, variant):
            assert target.read_text(encoding="utf-8") == "after\n"
        assert target.read_text(encoding="utf-8") == "before\n"
    finally:
        if target.exists():
            target.unlink()


def test_run_baseline_writes_split_results(tmp_path: Path, monkeypatch) -> None:
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_surface.md"
    config = write_config(tmp_path, surface_relpath=surface_relpath)
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
    surface_relpath = f"experiments/harness/surfaces/{tmp_path.name}_surface.md"
    proposer = tmp_path / "proposer.py"
    proposer.write_text(
        f"""
from pathlib import Path
import os

current = Path(os.environ["CODE2WORKSPACE_HARNESS_CURRENT"])
proposal = Path(os.environ["CODE2WORKSPACE_HARNESS_PROPOSAL"])
(current / "{Path(surface_relpath).name}").write_text("improved surface\\n", encoding="utf-8")
proposal.write_text("# Proposal\\n\\n- Summary: improve generic scores\\n", encoding="utf-8")
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

    def fake_evaluate_case(*, case, split_dir):  # noqa: ANN001
        current_prompt = surface_target.read_text(encoding="utf-8")
        score = 82.0 if current_prompt == "improved surface\n" else 70.0
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

    try:
        report = run_experiment(experiment=experiment, max_iterations=1)
    finally:
        if original is None:
            if surface_target.exists():
                surface_target.unlink()
        else:
            surface_target.write_text(original, encoding="utf-8")

    assert report.final.key == "iter-001"
    assert report.final_train.mean_score == 82.0
    assert report.final_holdout is not None
    assert report.final_holdout.mean_score == 82.0
