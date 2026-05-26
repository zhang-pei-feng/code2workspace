from __future__ import annotations

import json
from pathlib import Path

from code2workspace_cli.generic_experience_store import (
    GenericOrchestrationExperienceRecord,
    build_experience_record,
    experience_table_path,
    generated_guidance_path,
    load_experience_table,
    load_records,
    rebuild_distilled_guidance,
    rebuild_experience_table,
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


def _record(
    tmp_path: Path,
    *,
    case_id: str = "generic-local-trace",
    prompt: str = "请只基于本地代码，说明 generic trace 会记录什么，回答简短并保留证据边界。",
    run_name: str = "run-1",
) -> GenericOrchestrationExperienceRecord:
    run_dir = tmp_path / "workspace" / run_name
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
    return build_experience_record(
        case_id=case_id,
        prompt=prompt,
        split="train",
        variant="iter-001",
        harness_run_root=tmp_path / "harness-run",
        orchestration_run_dir=run_dir,
        generic_trace_summary=_summary_payload(),
        baseline_split_mean_score=80.0,
        candidate_split_mean_score=86.0,
    )


def test_build_write_and_load_generic_experience_record(tmp_path: Path) -> None:
    record = _record(tmp_path)

    path = write_record(record, root=tmp_path)
    loaded = load_records(root=tmp_path)
    table = load_experience_table(root=tmp_path)

    assert path.exists()
    assert len(loaded) == 1
    assert table is not None
    assert experience_table_path(tmp_path).exists()
    assert table.total_instance_count == 1
    assert table.pending_major_update_count == 1
    assert table.entries[0].classification == "local_code_explanation__local_only__repo_local"
    assert table.entries[0].instance_paths == [path.relative_to(tmp_path).as_posix()]
    assert table.entries[0].explain.startswith("Strategy:")
    assert "Observed successful shape" in table.entries[0].explain
    assert loaded[0].problem_classification.evidence_mode == "local_only"
    assert loaded[0].problem_abstraction.summary.startswith("Explain repo-local runtime")
    assert loaded[0].trajectory.node_ids == ["init_generic", "worker_context", "summarize"]
    assert loaded[0].trajectory_effect.score_delta_vs_previous == 6.0


def test_same_class_append_only_adds_instance_paths(tmp_path: Path) -> None:
    first = _record(tmp_path, run_name="run-1")
    first_path = write_record(first, root=tmp_path)
    table = load_experience_table(root=tmp_path)
    assert table is not None
    original_abstraction = table.entries[0].problem_abstraction
    original_explain = table.entries[0].explain

    second = _record(
        tmp_path,
        case_id="generic-local-trace-2",
        prompt="请只基于本地代码，解释 raw worker trace 和 tool activity 的差别。",
        run_name="run-2",
    )
    second.problem_abstraction.summary = "This later abstraction must wait for a major update."
    second.trajectory_explain = "This later explain must not replace the existing table row."
    second_path = write_record(second, root=tmp_path)

    table = load_experience_table(root=tmp_path)

    assert table is not None
    assert len(table.entries) == 1
    assert table.entries[0].problem_abstraction == original_abstraction
    assert table.entries[0].explain == original_explain
    assert table.entries[0].instance_count == 2
    assert table.entries[0].instance_paths == sorted(
        [first_path.relative_to(tmp_path).as_posix(), second_path.relative_to(tmp_path).as_posix()]
    )


def test_different_classification_adds_new_table_entry(tmp_path: Path) -> None:
    write_record(_record(tmp_path, run_name="run-1"), root=tmp_path)
    computed = _record(
        tmp_path,
        case_id="generic-computed",
        prompt="请计算 metric 差值并判断这个优化是否有效。",
        run_name="run-2",
    )
    write_record(computed, root=tmp_path)

    table = load_experience_table(root=tmp_path)

    assert table is not None
    assert len(table.entries) == 2
    assert {entry.classification for entry in table.entries} == {
        "computed_judgment__computed_local__generic",
        "local_code_explanation__local_only__repo_local",
    }


def test_twenty_appends_trigger_deterministic_major_update(tmp_path: Path) -> None:
    for index in range(20):
        write_record(
            _record(tmp_path, case_id=f"generic-local-{index}", run_name=f"run-{index}"),
            root=tmp_path,
        )

    table = load_experience_table(root=tmp_path)

    assert table is not None
    assert table.total_instance_count == 20
    assert table.pending_major_update_count == 0
    assert table.last_major_update_at is not None
    assert len(table.entries) == 1
    assert table.entries[0].instance_count == 20


def test_rebuild_experience_table_backfills_existing_records(tmp_path: Path) -> None:
    record = _record(tmp_path, run_name="run-1")
    records_base = tmp_path / ".code2workspace/skills/orchestration/generic-experience/records"
    records_base.mkdir(parents=True)
    record_path = records_base / f"{record.record_id}.json"
    record_path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert not experience_table_path(tmp_path).exists()
    fallback_lines = retrieve_experience_guidance_lines(
        task="请只基于本地代码说明 generic trace 记录了什么。",
        root=tmp_path,
    )

    table_path = rebuild_experience_table(root=tmp_path)
    table = load_experience_table(root=tmp_path)

    assert fallback_lines
    assert table_path == experience_table_path(tmp_path)
    assert table is not None
    assert table.total_instance_count == 1
    assert table.pending_major_update_count == 0
    assert table.entries[0].instance_paths == [record_path.relative_to(tmp_path).as_posix()]
    assert "minimum evidence boundary" in table.entries[0].explain


def test_rebuild_and_retrieve_experience_guidance(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        prompt="请只基于本地代码，解释 worker tool activity 和 raw worker trace 的差别，保持口语化。",
        run_name="run-2",
    )
    write_record(record, root=tmp_path)

    guidance_path = rebuild_distilled_guidance(root=tmp_path)
    guidance = guidance_path.read_text(encoding="utf-8")
    retrieved = retrieve_experience_guidance_lines(
        task="请只基于本地代码解释 raw worker trace 和 tool activity 的区别。",
        root=tmp_path,
    )

    assert guidance_path == generated_guidance_path(tmp_path)
    assert "Classification: local_code_explanation__local_only__repo_local" in guidance
    assert "Problem abstraction: Explain repo-local runtime" in guidance
    assert "Instance count: 1" in guidance
    assert retrieved
    assert any("Retrieved generic experience" in line for line in retrieved)
    assert any("Preferred trajectory from experience" in line for line in retrieved)
    assert any("Experience abstraction" in line for line in retrieved)
