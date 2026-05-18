"""Tests for supervisor artifact evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from code2workspace_cli.supervisor_evaluation import evaluate_supervisor_run


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_worker(run_dir: Path, node_id: str, result: dict[str, object]) -> None:
    _write_json(
        run_dir / "worker_outputs" / f"{node_id}.json",
        {
            "round_index": 1,
            "node": {"node_id": node_id},
            "result": result,
        },
    )


def test_evaluate_github2workspace_detects_reproducible_smoke_success(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-github"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "request.json", {"task": "repo task"})
    _write_json(
        run_dir / "final_decision.json",
        {"task_type": "github2workspace", "decision": "stop"},
    )
    _write_json(
        run_dir / "github_repo_materialization.json",
        {"selected_strategy": "code_repository_copy", "attempts": [{"status": "success"}]},
    )
    _write_worker(
        run_dir,
        "inspect",
        {"status": "completed", "summary": "repository inspected"},
    )
    dockerfile = tmp_path / "repo" / "Dockerfile"
    dockerfile.parent.mkdir()
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    _write_worker(
        run_dir,
        "build",
        {
            "status": "completed",
            "summary": "Docker image build succeeded.",
            "artifacts": [str(dockerfile)],
        },
    )
    smoke_dir = run_dir / "wdl_smoke_run" / "20260518_014156_Smoke"
    output_file = smoke_dir / "out.txt"
    output_file.parent.mkdir(parents=True)
    output_file.write_text("ok\n", encoding="utf-8")
    _write_json(smoke_dir / "outputs.json", {"Smoke.out": str(output_file)})
    (smoke_dir / "workflow.log").write_text("task complete exit_code: 0\n", encoding="utf-8")
    (run_dir / "final_response.md").write_text(
        "Smoke run succeeded and evidence is attached.",
        encoding="utf-8",
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.task_family == "github2workspace"
    assert result.completion_status == "completed"
    assert result.completion_level == "G8.workspace_reproducible"
    assert result.false_positive is False
    assert result.reproducible is True
    assert str(smoke_dir / "outputs.json") in result.evidence_paths


def test_evaluate_github2workspace_flags_smoke_success_false_positive(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-github-fp"
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "final_decision.json",
        {"task_type": "github2workspace", "decision": "stop"},
    )
    _write_json(
        run_dir / "github_repo_materialization.json",
        {"selected_strategy": "clone", "attempts": [{"status": "success"}]},
    )
    _write_worker(run_dir, "inspect", {"status": "completed", "summary": "inspected"})
    _write_worker(
        run_dir,
        "build",
        {"status": "completed", "summary": "Docker image build succeeded."},
    )
    (run_dir / "final_response.md").write_text(
        "端到端 workflow 已经成功跑通。",
        encoding="utf-8",
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.completion_status == "partial"
    assert result.completion_level == "G4.environment_built"
    assert result.false_positive is True
    assert result.unsupported_claims == [
        "final response claims workflow/smoke success without successful smoke-run evidence"
    ]


def test_evaluate_benchmark_detects_valid_multi_operator_comparison(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-benchmark"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "final_decision.json", {"task_type": "benchmark", "decision": "stop"})
    _write_json(
        run_dir / "operator_selection.json",
        {"selected_tools": ["spades", "megahit"], "dataset_key": "viral-reads"},
    )
    _write_json(
        run_dir / "dataset_resolution.json",
        {"repo_to_dataset": {"spades": "viral-reads", "megahit": "viral-reads"}},
    )
    rows = []
    for tool in ("spades", "megahit"):
        case_dir = run_dir / "cases" / tool
        output = case_dir / "run" / f"{tool}.fa"
        output.parent.mkdir(parents=True)
        output.write_text(">c\nAAAA\n", encoding="utf-8")
        (case_dir / "wdl").mkdir(parents=True)
        (case_dir / "wdl" / "workflow.wdl").write_text("workflow W {}", encoding="utf-8")
        _write_json(case_dir / "wdl" / "inputs.json", {"input": "reads.fq"})
        _write_json(case_dir / "manifest.json", {"dataset_key": "viral-reads"})
        _write_json(
            case_dir / "run" / "status.json",
            {"success": True, "returncode": 0, "output_artifacts": [str(output)]},
        )
        _write_json(
            case_dir / "run" / "result_manifest.json",
            {"expected_outputs": {"assembly": {"exists": True, "path": str(output)}}},
        )
        _write_json(case_dir / "analysis.json", {"metrics": {"n50": 1000 if tool == "spades" else 900}})
        rows.append({"repo": tool, "success": True, "metrics": {"n50": 1000}})
    _write_json(
        run_dir / "benchmark_supervisor_summary.json",
        {"comparison": {"best_n50": "spades", "overall": "spades has the highest N50."}, "rows": rows},
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.task_family == "benchmark"
    assert result.completion_status == "completed"
    assert result.completion_level == "B9.comparison_valid"
    assert result.selected_operators == ["spades", "megahit"]
    assert result.completed_operators == ["spades", "megahit"]
    assert result.dataset_consistency == "same_dataset"
    assert result.comparison_valid is True
    assert result.false_positive is False


def test_evaluate_benchmark_flags_false_fair_comparison_claim(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-benchmark-fp"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "final_decision.json", {"task_type": "benchmark", "decision": "stop"})
    _write_json(run_dir / "operator_selection.json", {"selected_tools": ["spades", "megahit"]})
    for tool, success in (("spades", True), ("megahit", False)):
        case_dir = run_dir / "cases" / tool
        _write_json(case_dir / "manifest.json", {"dataset_key": "viral-reads"})
        _write_json(case_dir / "wdl" / "inputs.json", {"input": "reads.fq"})
        _write_json(
            case_dir / "run" / "status.json",
            {"success": success, "returncode": 0 if success else 1},
        )
    (run_dir / "final_response.md").write_text(
        "这是一次公平比较，两个工具的优劣已经可以判断。",
        encoding="utf-8",
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.completion_status == "partial"
    assert result.false_positive is True
    assert "final response claims multi-operator comparison with fewer than two completed operators" in result.unsupported_claims
    assert "final response claims a valid/fair comparison without comparable multi-operator evidence" in result.unsupported_claims
