from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path


def _load_benchmark_workflow_module():
    repo_root = Path(__file__).resolve().parents[4]
    script_path = (
        repo_root
        / ".code2workspace"
        / "skills"
        / "orchestration"
        / "benchmark-workflow-orchestrator"
        / "scripts"
        / "benchmark_workflow.py"
    )
    spec = importlib.util.spec_from_file_location("benchmark_workflow_test_module", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_helper_summarize_materializes_wdl_history_record(tmp_path: Path) -> None:
    module = _load_benchmark_workflow_module()
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "20260518_helper_history"
    case_dir = run_dir / "cases" / "canu"
    wdl_dir = case_dir / "wdl"
    wdl_dir.mkdir(parents=True, exist_ok=True)
    reads = tmp_path / "pacbio.fastq"
    reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    staged_wdl = wdl_dir / "workflow.wdl"
    staged_wdl.write_text("workflow canu_workflow {}\n", encoding="utf-8")
    staged_inputs = wdl_dir / "inputs.json"
    staged_inputs.write_text(
        json.dumps({"canu_workflow.reads": str(reads)}),
        encoding="utf-8",
    )
    assembly = wdl_dir / "contigs.fasta"
    assembly.write_text(">contig\nACGT\n", encoding="utf-8")
    (wdl_dir / "outputs.json").write_text(
        json.dumps({"canu_workflow.contigs": str(assembly)}),
        encoding="utf-8",
    )
    (wdl_dir / "status.json").write_text(
        json.dumps(
            {
                "success": True,
                "returncode": 0,
                "workflow_path": str(staged_wdl),
                "inputs_path": str(staged_inputs),
                "outputs_path": str(wdl_dir / "outputs.json"),
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
    analysis_payload = {
        "family": "long-read-assembly",
        "artifact_paths": [str(assembly)],
        "artifact_checksums": {},
        "metrics": {"contig_count": 1, "assembly_size": 4, "n50": 4},
    }
    (case_dir / "analysis.json").write_text(json.dumps(analysis_payload), encoding="utf-8")
    (case_dir / "analysis.md").write_text("# analysis\n", encoding="utf-8")

    record_paths = module._materialize_benchmark_comparison_history_for_run(run_dir)

    assert len(record_paths) == 1
    record_path = (
        workspace_root
        / "benchmark_comparison_history_store"
        / "records"
        / "canu"
        / run_dir.name
        / "benchmark_result_record.json"
    )
    assert record_path.exists()
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["repo"] == "canu"
    assert payload["success"] is True
    assert payload["status_path"] == str(wdl_dir / "status.json")
    assert payload["wdl_status_path"] == str(wdl_dir / "status.json")
    assert payload["result_files"] == [str(assembly)]
    assert payload["metrics"] == {"contig_count": 1, "assembly_size": 4, "n50": 4}
    assert payload["workflow_signature"]
    assert payload["input_signature"]
    assert Path(payload["result_manifest_path"]).exists()


def test_helper_summarize_updates_analysis_status_in_summary_row(tmp_path: Path) -> None:
    module = _load_benchmark_workflow_module()
    workspace_root = tmp_path / "workspace"
    run_dir = workspace_root / "20260518_helper_summary_status"
    case_dir = run_dir / "cases" / "canu"
    wdl_dir = case_dir / "wdl"
    wdl_dir.mkdir(parents=True, exist_ok=True)
    reads = tmp_path / "pacbio.fastq"
    reads.write_text("@r\nACGT\n+\n!!!!\n", encoding="utf-8")
    staged_wdl = wdl_dir / "workflow.wdl"
    staged_wdl.write_text("workflow canu_workflow {}\n", encoding="utf-8")
    staged_inputs = wdl_dir / "inputs.json"
    staged_inputs.write_text(
        json.dumps({"canu_workflow.reads": str(reads)}),
        encoding="utf-8",
    )
    assembly = wdl_dir / "contigs.fasta"
    assembly.write_text(">contig\nACGT\n", encoding="utf-8")
    (wdl_dir / "status.json").write_text(
        json.dumps(
            {
                "success": True,
                "returncode": 0,
                "workflow_path": str(staged_wdl),
                "inputs_path": str(staged_inputs),
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
                "wdl_path": str(staged_wdl),
                "inputs_path": str(staged_inputs),
                "wdl_workflow_name": "canu_workflow",
                "selected_input_files": {"reads": str(reads)},
            }
        ),
        encoding="utf-8",
    )

    result = module.cmd_summarize(SimpleNamespace(run_dir=str(run_dir)))

    assert result == 0
    case_summary = json.loads((case_dir / "summary.json").read_text(encoding="utf-8"))
    run_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    case_manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    assert case_summary["analysis_status"] == "completed"
    assert run_summary["rows"][0]["analysis_status"] == "completed"
    assert case_manifest["phase_status"]["analysis"] == "completed"
