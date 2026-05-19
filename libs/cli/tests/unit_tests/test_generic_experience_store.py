from __future__ import annotations

import json
from pathlib import Path

from code2workspace_cli.generic_experience_store import (
    build_experience_record,
    generated_guidance_path,
    load_records,
    rebuild_distilled_guidance,
    retrieve_experience_guidance_lines,
    write_record,
)


def _summary_payload() -> dict[str, object]:
    return {
        "completion_status": "completed",
        "completion_level": "D6.evidence_boundary_preserved",
        "metrics": {
            "graph_shape_label": "direct_or_minimal",
            "round_count": 2,
            "node_count": 3,
            "tool_event_count": 12,
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


def test_build_write_and_load_generic_experience_record(tmp_path: Path) -> None:
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
    record = build_experience_record(
        case_id="generic-local-trace",
        prompt="请只基于本地代码，说明 generic trace 会记录什么，回答简短并保留证据边界。",
        split="train",
        variant="iter-001",
        harness_run_root=tmp_path / "harness-run",
        orchestration_run_dir=run_dir,
        generic_trace_summary=_summary_payload(),
        baseline_split_mean_score=80.0,
        candidate_split_mean_score=86.0,
    )

    path = write_record(record, root=tmp_path)
    loaded = load_records(root=tmp_path)

    assert path.exists()
    assert len(loaded) == 1
    assert loaded[0].problem_classification.evidence_mode == "local_only"
    assert loaded[0].problem_abstraction.summary.startswith("Explain repo-local runtime")
    assert loaded[0].trajectory.node_ids == ["init_generic", "worker_context", "summarize"]
    assert loaded[0].trajectory_effect.score_delta_vs_previous == 6.0


def test_rebuild_and_retrieve_experience_guidance(tmp_path: Path) -> None:
    run_dir = tmp_path / "workspace" / "run-2"
    run_dir.mkdir(parents=True)
    (run_dir / "graph_round_2.json").write_text(
        json.dumps(
            {
                "graph": {
                    "nodes": [
                        {"node_id": "init_generic"},
                        {"node_id": "worker_context"},
                        {"node_id": "compose_generic"},
                        {"node_id": "summarize"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    record = build_experience_record(
        case_id="generic-local-trace",
        prompt="请只基于本地代码，解释 worker tool activity 和 raw worker trace 的差别，保持口语化。",
        split="holdout",
        variant="iter-002",
        harness_run_root=tmp_path / "harness-run",
        orchestration_run_dir=run_dir,
        generic_trace_summary=_summary_payload(),
        baseline_split_mean_score=81.0,
        candidate_split_mean_score=87.5,
    )
    write_record(record, root=tmp_path)

    guidance_path = rebuild_distilled_guidance(root=tmp_path)
    guidance = guidance_path.read_text(encoding="utf-8")
    retrieved = retrieve_experience_guidance_lines(
        task="请只基于本地代码解释 raw worker trace 和 tool activity 的区别。",
        root=tmp_path,
    )

    assert guidance_path == generated_guidance_path(tmp_path)
    assert "Preferred trajectory" in guidance
    assert "Why it worked" in guidance
    assert retrieved
    assert any("Retrieved generic experience" in line for line in retrieved)
    assert any("Preferred trajectory from experience" in line for line in retrieved)
