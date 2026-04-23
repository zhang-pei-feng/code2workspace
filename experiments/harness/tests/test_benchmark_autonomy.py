from __future__ import annotations

import json
from pathlib import Path

from experiments.harness.code2workspace_harness.benchmark_autonomy import (
    build_benchmark_autonomy_prompt,
    load_benchmark_autonomy_experiment,
    prepare_benchmark_autonomy_run,
    run_benchmark_autonomy_case,
)
from experiments.harness.code2workspace_harness.core import repo_root


CONFIG_PATH = (
    repo_root()
    / "experiments"
    / "harness"
    / "configs"
    / "benchmark_autonomy_phase1.toml"
)


def test_load_benchmark_autonomy_experiment_reads_phase1_families_and_levels() -> None:
    experiment = load_benchmark_autonomy_experiment(CONFIG_PATH)

    assert experiment.name == "benchmark-autonomy-phase1"
    assert tuple(experiment.families) == ("short-read-assembly", "long-read-assembly")
    assert tuple(experiment.levels) == ("level1", "level2", "level3", "level4")

    short_read = experiment.families["short-read-assembly"]
    long_read = experiment.families["long-read-assembly"]

    assert short_read.tool_candidates == ("spades", "megahit")
    assert short_read.fixed_tools == ("spades", "megahit")
    assert short_read.dataset_candidates == ("short-read-ecoli-srr001666",)
    assert long_read.tool_candidates == ("canu", "Flye")
    assert long_read.dataset_candidates == ("long-read-ecoli-pacbio",)

    level1 = experiment.levels["level1"]
    level2 = experiment.levels["level2"]
    level3 = experiment.levels["level3"]
    level4 = experiment.levels["level4"]

    assert level1.tool_policy == "fixed"
    assert level1.input_policy == "fixed"
    assert level1.wdl_policy == "fixed"
    assert level1.wdl_edit_mode == "none"

    assert level2.tool_policy == "agent-choice"
    assert level2.input_policy == "fixed"
    assert level2.wdl_policy == "fixed"

    assert level3.tool_policy == "agent-choice"
    assert level3.input_policy == "agent-choice"
    assert level3.wdl_policy == "fixed"

    assert level4.tool_policy == "agent-choice"
    assert level4.input_policy == "agent-choice"
    assert level4.wdl_policy == "editable"
    assert level4.wdl_edit_mode == "run-copy"
    assert level4.optional_wdl_edit_modes == ("direct-source",)


def test_prepare_benchmark_autonomy_run_stages_isolated_workspace_and_inputs(
    tmp_path: Path,
) -> None:
    experiment = load_benchmark_autonomy_experiment(CONFIG_PATH)

    prepared = prepare_benchmark_autonomy_run(
        experiment=experiment,
        family_id="long-read-assembly",
        level_id="level1",
        output_root=tmp_path,
    )

    marker = prepared.workspace_root / ".code2workspace" / "project-root.txt"
    assert marker.exists()
    assert marker.read_text(encoding="utf-8").strip() == str(repo_root())

    assert not (prepared.workspace_root / "results").exists()
    assert not (prepared.workspace_root / ".workspaces").exists()
    assert not (prepared.workspace_root / "workspace").exists()

    staged_reads = prepared.dataset_root / "long-read-ecoli-pacbio" / "pacbio.fastq"
    assert staged_reads.exists()

    copied_case_dirs = sorted(path.name for path in prepared.case_root.iterdir() if path.is_dir())
    assert copied_case_dirs == ["002_canu", "004_Flye"]

    canu_inputs = json.loads((prepared.case_root / "002_canu" / "inputs.json").read_text(encoding="utf-8"))
    flye_inputs = json.loads((prepared.case_root / "004_Flye" / "inputs.json").read_text(encoding="utf-8"))
    assert canu_inputs["CanuWorkflow.reads_fastq"] == str(staged_reads)
    assert flye_inputs["FlyeAssembly.reads"] == str(staged_reads)


def test_build_benchmark_autonomy_prompt_reflects_level_policies(tmp_path: Path) -> None:
    experiment = load_benchmark_autonomy_experiment(CONFIG_PATH)

    level1 = prepare_benchmark_autonomy_run(
        experiment=experiment,
        family_id="short-read-assembly",
        level_id="level1",
        output_root=tmp_path / "level1",
    )
    level3 = prepare_benchmark_autonomy_run(
        experiment=experiment,
        family_id="short-read-assembly",
        level_id="level3",
        output_root=tmp_path / "level3",
    )
    level4 = prepare_benchmark_autonomy_run(
        experiment=experiment,
        family_id="short-read-assembly",
        level_id="level4",
        output_root=tmp_path / "level4",
    )

    prompt1 = build_benchmark_autonomy_prompt(level1)
    prompt3 = build_benchmark_autonomy_prompt(level3)
    prompt4 = build_benchmark_autonomy_prompt(level4)

    assert "fixed tool set" in prompt1
    assert "Do not modify the staged WDL files" in prompt1
    assert "fixed input files" in prompt1

    assert "choose one or more tools" in prompt3
    assert "choose the exact input files from the staged dataset directory" in prompt3
    assert "Do not modify the staged WDL files" in prompt3

    assert "You may modify the staged WDL copies" in prompt4
    assert "default edit mode is run-local copy" in prompt4
    assert str(level4.report_json_path) in prompt4
    assert str(level4.report_md_path) in prompt4


def test_run_benchmark_autonomy_case_writes_summary_even_on_partial_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = load_benchmark_autonomy_experiment(CONFIG_PATH)
    prepared = prepare_benchmark_autonomy_run(
        experiment=experiment,
        family_id="short-read-assembly",
        level_id="level2",
        output_root=tmp_path,
    )

    def fake_run(command, *, cwd, capture_output, text, timeout, check):  # noqa: ANN001
        del command, cwd, capture_output, text, timeout, check
        prepared.report_json_path.write_text(
            json.dumps(
                {
                    "selected_tools": ["spades"],
                    "selected_inputs": [str(prepared.dataset_root / "short-read-ecoli-srr001666" / "SRR001666_1.fastq.gz")],
                    "wdl_modified": False,
                    "wdl_changes": [],
                    "tool_outcomes": [
                        {
                            "tool": "spades",
                            "completion_state": "completed",
                            "artifact_paths": ["/tmp/contigs.fasta"],
                            "failure_category": None,
                        },
                        {
                            "tool": "megahit",
                            "completion_state": "failed",
                            "artifact_paths": [],
                            "failure_category": "environment/missing dependency",
                        },
                    ],
                    "comparison_summary": "spades succeeded while megahit was blocked",
                    "blockers": ["megahit image missing"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        prepared.report_md_path.write_text("# Agent report\n", encoding="utf-8")
        return type(
            "Completed",
            (),
            {"returncode": 1, "stdout": "Calling tool: execute\n", "stderr": "megahit: command not found\n"},
        )()

    monkeypatch.setattr(
        "experiments.harness.code2workspace_harness.benchmark_autonomy.subprocess.run",
        fake_run,
    )

    result = run_benchmark_autonomy_case(prepared)

    assert result.summary_json_path.exists()
    assert result.summary_md_path.exists()
    payload = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert payload["selected_tools"] == ["spades"]
    assert payload["wdl_modified"] is False
    assert payload["cost_metrics"]["command_count"] == 1
    assert payload["tool_outcomes"][1]["failure_category"] == "environment/missing dependency"
    assert payload["user_report_path"] == str(prepared.report_md_path)


def test_run_benchmark_autonomy_case_preserves_nested_agent_report_shapes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    experiment = load_benchmark_autonomy_experiment(CONFIG_PATH)
    prepared = prepare_benchmark_autonomy_run(
        experiment=experiment,
        family_id="short-read-assembly",
        level_id="level1",
        output_root=tmp_path,
    )

    def fake_run(command, *, cwd, capture_output, text, timeout, check):  # noqa: ANN001
        del command, cwd, capture_output, text, timeout, check
        prepared.report_json_path.write_text(
            json.dumps(
                {
                    "selected_tools": [
                        {
                            "tool": "spades",
                            "case_dir": "/tmp/case",
                        }
                    ],
                    "selected_inputs": {
                        "dataset_key": "short-read-ecoli-srr001666",
                        "files": ["/tmp/r1.fastq.gz", "/tmp/r2.fastq.gz"],
                    },
                    "wdl_modified": False,
                    "wdl_changes": [],
                    "tool_outcomes": [
                        {
                            "tool": "spades",
                            "completion_state": "succeeded",
                            "artifact_paths": ["/tmp/contigs.fasta"],
                            "failure_category": None,
                        }
                    ],
                    "comparison_summary": {
                        "comparison_group": "shared-short-read-assembly",
                        "summary": ["spades only"],
                    },
                    "blockers": [
                        {
                            "tool": "all",
                            "category": "wdl_runner_unavailable",
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        prepared.report_md_path.write_text("# Agent report\n", encoding="utf-8")
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "Calling tool: execute\n", "stderr": ""},
        )()

    monkeypatch.setattr(
        "experiments.harness.code2workspace_harness.benchmark_autonomy.subprocess.run",
        fake_run,
    )

    result = run_benchmark_autonomy_case(prepared)

    payload = json.loads(result.summary_json_path.read_text(encoding="utf-8"))
    assert payload["selected_tools"] == [{"tool": "spades", "case_dir": "/tmp/case"}]
    assert payload["selected_inputs"] == {
        "dataset_key": "short-read-ecoli-srr001666",
        "files": ["/tmp/r1.fastq.gz", "/tmp/r2.fastq.gz"],
    }
    assert payload["tool_outcomes"][0]["completion_state"] == "succeeded"
    assert payload["tool_outcomes"][0]["failure_category"] is None
    assert payload["comparison_summary"] == {
        "comparison_group": "shared-short-read-assembly",
        "summary": ["spades only"],
    }
    assert payload["blockers"] == [{"tool": "all", "category": "wdl_runner_unavailable"}]
