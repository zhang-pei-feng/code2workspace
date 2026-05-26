from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from code2workspace_cli.generic_experience_store import (
    experience_table_path,
    rebuild_distilled_guidance as actual_rebuild_distilled_guidance,
)
from code2workspace_cli.generic_experience_store import write_record as actual_write_record
from experiments.harness.generic_orchestration_harness.core import (
    CandidateEvaluation,
    CaseScoreResult,
    Experiment,
    GenericCase,
    Proposal,
    RunLayout,
    SplitScore,
)
from experiments.harness.generic_orchestration_harness.runner import (
    _export_accepted_candidate_experience,
    sync_experience_skill_from_run_root,
)


def test_export_accepted_candidate_experience_writes_records_and_generated_skill(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "workspace" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "graph_round_2.json").write_text(
        json.dumps(
            {
                "graph": {
                    "nodes": [
                        {"node_id": "init_generic"},
                        {"node_id": "worker_context"},
                        {"node_id": "summarize"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    summary_path = run_dir / "generic_trace_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "completion_status": "completed",
                "completion_level": "D6.evidence_boundary_preserved",
                "metrics": {
                    "graph_shape_label": "direct_or_minimal",
                    "round_count": 2,
                    "node_count": 3,
                    "tool_event_count": 10,
                    "source_url_count": 0,
                    "has_evidence_boundary": True,
                },
                "scores": {
                    "routing_score": 100,
                    "graph_fit_score": 90,
                    "traceability_score": 100,
                    "evidence_score": 85,
                    "answer_score": 80,
                    "efficiency_score": 95,
                },
                "findings": ["Generic trace is complete enough for harness comparison."],
            }
        ),
        encoding="utf-8",
    )
    experiment = Experiment(
        path=tmp_path / "config.toml",
        name="generic-skill-loop",
        output_root=tmp_path / "runs",
        max_iterations=1,
        max_parallel_cases=1,
        cases=(
            GenericCase(
                case_id="generic-train",
                prompt="请只基于本地代码，说明 generic trace 会记录什么，回答简短。",
                split="train",
                weight=1.0,
                max_runtime_minutes=5,
            ),
            GenericCase(
                case_id="generic-holdout",
                prompt="请只基于本地代码，解释 raw worker trace 和 tool activity 的差别。",
                split="holdout",
                weight=1.0,
                max_runtime_minutes=5,
            ),
        ),
    )
    layout = RunLayout(output_root=tmp_path / "runs", experiment_name="generic-skill-loop", run_id="20260519T020000Z")
    outcome = CaseScoreResult(
        case_id="generic-train",
        split="train",
        weight=1.0,
        status="passed",
        returncode=0,
        completion_status="completed",
        completion_level="D6.evidence_boundary_preserved",
        overall_score=88.0,
        component_scores={
            "routing_score": 100.0,
            "graph_fit_score": 90.0,
            "traceability_score": 100.0,
            "evidence_score": 85.0,
            "answer_score": 80.0,
            "efficiency_score": 95.0,
        },
        findings=("Generic trace is complete enough for harness comparison.",),
        run_dir=str(run_dir),
        generic_trace_summary_path=str(summary_path),
        evaluation_path=str(run_dir / "evaluation.json"),
        stdout_path=str(run_dir / "stdout.txt"),
        stderr_path=str(run_dir / "stderr.txt"),
    )
    candidate = CandidateEvaluation(
        variant="iter-001",
        proposal=Proposal(changed_surfaces=(), workspace_dir=str(tmp_path), summary="improve"),
        train=SplitScore(
            split="train",
            variant="iter-001",
            mean_score=88.0,
            total_weight=1.0,
            component_means={"traceability_score": 100.0},
            outcomes=(outcome,),
        ),
        holdout=SplitScore(
            split="holdout",
            variant="iter-001",
            mean_score=87.0,
            total_weight=1.0,
            component_means={"traceability_score": 100.0},
            outcomes=(),
        ),
        accepted=True,
        reason="improved",
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.write_record",
        lambda record: actual_write_record(record, root=tmp_path),
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.rebuild_distilled_guidance",
        lambda: actual_rebuild_distilled_guidance(root=tmp_path),
    )

    written = _export_accepted_candidate_experience(
        experiment=experiment,
        layout=layout,
        candidate=candidate,
        previous_train=SplitScore(
            split="train",
            variant="baseline",
            mean_score=80.0,
            total_weight=1.0,
            component_means={"traceability_score": 100.0},
            outcomes=(),
        ),
        previous_holdout=SplitScore(
            split="holdout",
            variant="baseline",
            mean_score=79.0,
            total_weight=1.0,
            component_means={"traceability_score": 100.0},
            outcomes=(),
        ),
    )

    assert written
    assert written[0].exists()
    table = json.loads(experience_table_path(tmp_path).read_text(encoding="utf-8"))
    assert table["total_instance_count"] == 1
    assert table["entries"][0]["instance_paths"] == [written[0].relative_to(tmp_path).as_posix()]
    assert (tmp_path / ".code2workspace/skills/orchestration/generic-experience/generated/generic_orchestration_experience.md").exists()


def test_sync_experience_skill_from_historical_run_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_root = tmp_path / "generic-harness-run"
    orchestration_run_dir = tmp_path / "workspace" / "run-2"
    orchestration_run_dir.mkdir(parents=True)
    (orchestration_run_dir / "graph_round_2.json").write_text(
        json.dumps({"graph": {"nodes": [{"node_id": "init_generic"}, {"node_id": "summarize"}]}}),
        encoding="utf-8",
    )
    summary_path = orchestration_run_dir / "generic_trace_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "completion_status": "completed",
                "completion_level": "D6.evidence_boundary_preserved",
                "metrics": {
                    "graph_shape_label": "direct_or_minimal",
                    "round_count": 2,
                    "node_count": 2,
                    "tool_event_count": 8,
                    "source_url_count": 0,
                    "has_evidence_boundary": True,
                },
                "scores": {
                    "routing_score": 100,
                    "graph_fit_score": 90,
                    "traceability_score": 100,
                    "evidence_score": 85,
                    "answer_score": 80,
                    "efficiency_score": 95,
                },
                "findings": ["Generic trace is complete enough for harness comparison."],
            }
        ),
        encoding="utf-8",
    )
    run_root.mkdir(parents=True)
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "generic-train",
                        "prompt": "请只基于本地代码，说明 generic trace 会记录什么。",
                        "split": "train",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_root / "report.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-19T02:00:00+00:00",
                "baseline_train": {"mean_score": 80.0},
                "baseline_holdout": {"mean_score": 79.0},
                "iterations": [
                    {
                        "candidate": {
                            "accepted": True,
                            "variant": "iter-001",
                            "train": {
                                "mean_score": 88.0,
                                "outcomes": [
                                    {
                                        "case_id": "generic-train",
                                        "run_dir": str(orchestration_run_dir),
                                        "generic_trace_summary_path": str(summary_path),
                                    }
                                ],
                            },
                            "holdout": {"mean_score": 87.0, "outcomes": []},
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.write_record",
        lambda record: actual_write_record(record, root=tmp_path),
    )
    monkeypatch.setattr(
        "experiments.harness.generic_orchestration_harness.runner.rebuild_distilled_guidance",
        lambda: actual_rebuild_distilled_guidance(root=tmp_path),
    )

    written = sync_experience_skill_from_run_root(run_root)

    assert len(written) == 1
    assert written[0].exists()
    table = json.loads(experience_table_path(tmp_path).read_text(encoding="utf-8"))
    assert table["total_instance_count"] == 1
    assert table["entries"][0]["instance_paths"] == [written[0].relative_to(tmp_path).as_posix()]
