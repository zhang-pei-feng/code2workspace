from __future__ import annotations

import json
from pathlib import Path

from experiments.harness.generate_thesis_asset_notes import (
    build_asset_notes,
    build_markdown_summary,
    write_summary_bundle,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_build_asset_notes_summarizes_three_ready_assets(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark.json"
    project_skill = tmp_path / "project-skill.json"
    two_hour = tmp_path / "two-hour.json"
    oneshot = tmp_path / "oneshot.json"
    swebench = tmp_path / "swebench.json"
    _write_json(
        benchmark,
        {
            "title": "Benchmark",
            "rows": [
                {"tool": "SPAdes", "dataset_group": "short-read", "status": "成功", "key_metrics_or_artifacts": "ok", "notes": "ok"},
                {"tool": "MEGAHIT", "dataset_group": "short-read", "status": "成功", "key_metrics_or_artifacts": "ok", "notes": "ok"},
                {"tool": "v-pipe", "dataset_group": "sars", "status": "失败", "key_metrics_or_artifacts": "none", "notes": "blocked"},
            ],
        },
    )
    _write_json(
        project_skill,
        {
            "title": "Project skill",
            "rows": [
                {"case": "a", "status": "passed", "task_type": "benchmark", "selected_skill": "benchmark-workflow-orchestrator", "lane_summary": "benchmark,analysis,synthesis", "phase_summary": ""},
                {"case": "b", "status": "passed", "task_type": "paper2workspace", "selected_skill": "paper2workspace-orchestrator", "lane_summary": "workspace,analysis,synthesis", "phase_summary": ""},
                {"case": "c", "status": "passed", "task_type": "multi-lane", "selected_skill": "none", "lane_summary": "workspace,benchmark,synthesis", "phase_summary": ""},
                {"case": "d", "status": "passed", "task_type": "", "selected_skill": "", "lane_summary": "", "phase_summary": "phase1=completed;phase2=completed;analysis=completed"},
            ],
        },
    )
    _write_json(
        two_hour,
        {
            "title": "Two hour",
            "rows": [
                {"repo": "spades", "channel": "clean harness baseline", "status": "completed", "completed": True, "failed_checks": []},
                {"repo": "megahit", "channel": "direct retry", "status": "completed", "completed": True, "failed_checks": []},
                {"repo": "v-pipe", "channel": "direct spotcheck", "status": "timed_out", "completed": False, "failed_checks": ["not_timed_out"]},
                {"repo": "fieldbioinformatics", "channel": "direct spotcheck", "status": "timed_out", "completed": False, "failed_checks": ["not_timed_out"]},
            ],
        },
    )
    _write_json(
        oneshot,
        {
            "title": "One-shot",
            "rows": [
                {"repo": "spades", "run_id": "20260416T123616Z", "duration": "26m42s", "status": "finished", "completed": False, "result_note": "首次进入真实 docker build"},
                {"repo": "v-pipe", "run_id": "20260417T010342Z", "duration": "25m28s", "status": "completed", "completed": True, "result_note": "历史 one-shot 正向基线"},
                {"repo": "fieldbioinformatics", "run_id": "20260417T014050Z", "duration": "16m16s", "status": "completed", "completed": True, "result_note": "历史 one-shot 正向基线"},
            ],
        },
    )
    _write_json(
        swebench,
        {
            "title": "SWE-bench Lite pilot",
            "rows": [
                {
                    "run_id": "pilot-001",
                    "dataset_name": "princeton-nlp/SWE-bench_Lite",
                    "subset_name": "dev",
                    "subset_size": 1,
                    "attempted": 1,
                    "resolved": 1,
                    "resolved_rate": "100.0%",
                    "patch_generated": 1,
                    "avg_runtime_per_task_seconds": 120.0,
                    "notes": "pilot subset; max_workers=1",
                },
                {
                    "run_id": "pilot-002",
                    "dataset_name": "princeton-nlp/SWE-bench_Lite",
                    "subset_name": "dev",
                    "subset_size": 1,
                    "attempted": 1,
                    "resolved": 0,
                    "resolved_rate": "0.0%",
                    "patch_generated": 1,
                    "avg_runtime_per_task_seconds": 80.0,
                    "notes": "pilot subset; max_workers=1",
                },
                {
                    "run_id": "pilot-003",
                    "dataset_name": "princeton-nlp/SWE-bench_Lite",
                    "subset_name": "dev",
                    "subset_size": 1,
                    "attempted": 1,
                    "resolved": 1,
                    "resolved_rate": "100.0%",
                    "patch_generated": 1,
                    "avg_runtime_per_task_seconds": 160.0,
                    "notes": "pilot subset; max_workers=1",
                }
            ],
        },
    )

    notes = build_asset_notes(
        oneshot_summary_path=oneshot,
        benchmark_summary_path=benchmark,
        project_skill_summary_path=project_skill,
        two_hour_summary_path=two_hour,
        swebench_summary_path=swebench,
    )

    assert [note["asset_id"] for note in notes] == [
        "table_5_2",
        "figure_5_1",
        "figure_5_2",
        "table_5_3",
        "figure_5_3",
        "table_5_7",
        "table_5_8",
        "table_5_9",
        "table_5_10",
    ]
    assert "3 个历史 one-shot run" in notes[0]["caption"]
    assert "completion_level" in notes[1]["caption"]
    assert "failure_category" in notes[2]["caption"]
    assert "3 条 pilot 运行" in notes[3]["caption"]
    assert "resolved=`2`" in notes[3]["caption"]
    assert "resolved / attempted = `2` / `3`" in notes[4]["caption"]
    assert "2 条 official resolved 样本" in notes[3]["interpretation"]
    assert "规划摘要" in notes[5]["caption"]
    assert "低成本回归层" in notes[5]["interpretation"]
    assert "4 个 case" in notes[6]["caption"]
    assert "`spades`" in notes[7]["interpretation"]
    assert "`megahit`" in notes[7]["interpretation"]
    assert "3 个 benchmark 工具" in notes[8]["caption"]


def test_build_markdown_summary_renders_sections() -> None:
    markdown = build_markdown_summary(
        [
            {
                "asset_id": "table_5_8",
                "asset_name": "表 5-8 project-skill 编排结果表",
                "caption": "caption",
                "interpretation": "interpretation",
                "source_summary": "/tmp/source.json",
            }
        ],
        title="Asset notes",
    )

    assert "# Asset notes" in markdown
    assert "## 表 5-8 project-skill 编排结果表" in markdown
    assert "- Caption: caption" in markdown


def test_write_summary_bundle_writes_json_and_markdown(tmp_path: Path) -> None:
    notes = [
        {
            "asset_id": "table_5_8",
            "asset_name": "表 5-8 project-skill 编排结果表",
            "caption": "caption",
            "interpretation": "interpretation",
            "source_summary": "/tmp/source.json",
        }
    ]

    output_dir = tmp_path / "bundle"
    write_summary_bundle(output_dir, notes, title="Asset notes")

    payload = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "SUMMARY_ZH.md").read_text(encoding="utf-8")

    assert payload["notes"][0]["asset_id"] == "table_5_8"
    assert "# Asset notes" in markdown
