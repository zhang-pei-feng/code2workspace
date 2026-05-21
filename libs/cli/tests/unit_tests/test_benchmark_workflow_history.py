from __future__ import annotations

import json
from pathlib import Path

from code2workspace_cli import supervisor_runtime


def test_internal_summary_materializes_wdl_history_record(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "20260518_helper_history"
    case_dir = run_dir / "cases" / "canu"
    wdl_dir = case_dir / "wdl"
    run_case_dir = case_dir / "run"
    wdl_dir.mkdir(parents=True, exist_ok=True)
    run_case_dir.mkdir(parents=True, exist_ok=True)
    reads = tmp_path / "pacbio.fastq"
    reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    staged_wdl = wdl_dir / "workflow.wdl"
    staged_wdl.write_text("workflow canu_workflow {}\n", encoding="utf-8")
    staged_inputs = wdl_dir / "inputs.json"
    staged_inputs.write_text(
        json.dumps({"canu_workflow.reads": str(reads)}),
        encoding="utf-8",
    )
    assembly = run_case_dir / "contigs.fasta"
    assembly.write_text(">contig\nACGT\n", encoding="utf-8")
    (run_case_dir / "status.json").write_text(
        json.dumps(
            {
                "success": True,
                "returncode": 0,
                "output_dir": str(run_case_dir),
                "output_artifacts": [str(assembly)],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "case_order": ["canu"],
                "benchmark_root": str(tmp_path / "benchmark-root"),
            }
        ),
        encoding="utf-8",
    )
    case_manifest = {
        "repo_name": "canu",
        "operator_id": "github2workspace:canu",
        "dataset_key": "long-read-canu-pacbio",
        "family": "long-read-assembly",
        "metric_keys": ["contig_count", "assembly_size", "n50"],
        "expected_outputs": ["contigs.fasta"],
        "phase_status": {"summary": "pending"},
        "wdl_path": str(staged_wdl),
        "inputs_path": str(staged_inputs),
        "wdl_workflow_name": "canu_workflow",
        "selected_input_files": {"reads": str(reads)},
    }
    (case_dir / "manifest.json").write_text(json.dumps(case_manifest), encoding="utf-8")

    analysis_json, analysis_md = supervisor_runtime._ensure_benchmark_analysis(
        repo="canu",
        run_dir=run_dir,
    )
    assert analysis_json.exists()
    assert analysis_md.exists()
    result_manifest = supervisor_runtime._write_benchmark_result_manifest(
        repo="canu",
        case_dir=case_dir,
        status_payload=json.loads((run_case_dir / "status.json").read_text(encoding="utf-8")),
    )
    record_path = supervisor_runtime._materialize_benchmark_result_record(
        repo="canu",
        run_dir=run_dir,
        case_dir=case_dir,
        manifest=case_manifest,
        status_payload=json.loads((run_case_dir / "status.json").read_text(encoding="utf-8")),
        result_manifest=result_manifest,
    )

    assert record_path is not None
    assert record_path.exists()
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["repo"] == "canu"
    assert payload["success"] is True
    assert payload["result_files"] == [str(assembly)]
    assert payload["workflow_signature"]
    assert payload["input_signature"]
    assert Path(payload["result_manifest_path"]).exists()


def test_internal_summary_updates_analysis_status_in_summary_row(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "20260518_helper_summary_status"
    case_dir = run_dir / "cases" / "canu"
    output_dir = case_dir / "run"
    output_dir.mkdir(parents=True, exist_ok=True)
    contigs = output_dir / "contigs.fasta"
    contigs.write_text(">contig\nACGT\n", encoding="utf-8")
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {
                "repo_name": "canu",
                "operator_id": "github2workspace:canu",
                "dataset_key": "long-read-canu-pacbio",
                "family": "long-read-assembly",
                "metric_keys": ["contig_count", "assembly_size", "n50"],
                "expected_outputs": ["contigs.fasta"],
                "phase_status": {"analysis": "pending", "summary": "pending"},
                "wdl_path": str(case_dir / "wdl" / "workflow.wdl"),
                "inputs_path": str(case_dir / "wdl" / "inputs.json"),
                "wdl_workflow_name": "canu_workflow",
                "selected_input_files": {"reads": str(tmp_path / "pacbio.fastq")},
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "status.json").write_text(
        json.dumps(
            {
                "success": True,
                "returncode": 0,
                "output_dir": str(output_dir),
                "output_artifacts": [str(contigs)],
            }
        ),
        encoding="utf-8",
    )

    node = supervisor_runtime.TaskNode(
        node_id="summarize",
        title="Summarize benchmark outcomes",
        objective="summarize",
        capability_bundles=["metric_compute", "summarize"],
        metadata={
            "task_type": "benchmark",
            "task": "summary",
            "run_dir": str(run_dir),
            "selected_tools": ["canu"],
        },
    )

    result = supervisor_runtime._run_deterministic_benchmark_summary(
        node=node,
        workspace_root=workspace_root,
    )

    assert result.status == "completed"
    run_summary = json.loads((run_dir / "benchmark_supervisor_summary.json").read_text(encoding="utf-8"))
    case_manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    assert run_summary["rows"][0]["success"] is True
    assert case_manifest["phase_status"]["analysis"] == "completed"
