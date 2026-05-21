"""Tests for supervisor artifact evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from code2workspace_cli.supervisor_evaluation import evaluate_supervisor_run, write_evaluation_for_run


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


def _append_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
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


def test_evaluate_benchmark_allows_scoped_same_dataset_success_comparison_claim(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-benchmark-scoped-fairness"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "final_decision.json", {"task_type": "benchmark", "decision": "stop"})
    _write_json(
        run_dir / "operator_selection.json",
        {"selected_tools": ["Flye", "canu"], "dataset_key": "long-read-canu-pacbio-real-tests"},
    )
    _write_json(
        run_dir / "dataset_resolution.json",
        {"repo_to_dataset": {"Flye": "long-read-canu-pacbio-real-tests", "canu": "long-read-canu-pacbio-real-tests"}},
    )
    rows = []
    for tool in ("Flye", "canu"):
        case_dir = run_dir / "cases" / tool
        output = case_dir / "run" / f"{tool}.fa"
        output.parent.mkdir(parents=True)
        output.write_text(">c\nAAAA\n", encoding="utf-8")
        (case_dir / "wdl").mkdir(parents=True)
        (case_dir / "wdl" / "inputs.json").write_text("{}", encoding="utf-8")
        _write_json(case_dir / "manifest.json", {"dataset_key": "long-read-canu-pacbio-real-tests"})
        _write_json(
            case_dir / "result_manifest.json",
            {
                "status": "completed",
                "outputs": {"primary": {"path": str(output), "exists": True, "size_bytes": 6}},
            },
        )
        _write_json(
            case_dir / "analysis.json",
            {"status": "completed", "metrics": {}, "checks": {"contigs_present": True}},
        )
        _write_worker(run_dir, tool, {"status": "completed", "summary": f"{tool} completed"})
        rows.append({"repo": tool, "success": True, "metrics": {}})
    _write_json(run_dir / "benchmark_supervisor_summary.json", {"comparison": None, "rows": rows})
    (run_dir / "final_response.md").write_text(
        (
            "Flye 和 canu 都在同一数据集上跑通了，所以可以公平比较谁有没有跑成功；"
            "但目前不能下更优结论，也不能判断谁更好。"
        ),
        encoding="utf-8",
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.completion_level == "B7.multi_operator_completed"
    assert result.false_positive is False
    assert result.unsupported_claims == []


def test_evaluate_benchmark_agent_owned_cases_without_run_status_count_as_completed(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-benchmark-agent-owned"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "final_decision.json", {"task_type": "benchmark", "decision": "stop"})
    _write_json(
        run_dir / "operator_selection.json",
        {"selected_tools": ["Flye", "canu"], "dataset_key": "long-read-canu-pacbio-real-tests"},
    )
    _write_json(
        run_dir / "dataset_resolution.json",
        {"repo_to_dataset": {"Flye": "long-read-canu-pacbio-real-tests", "canu": "long-read-canu-pacbio-real-tests"}},
    )
    for tool in ("Flye", "canu"):
        case_dir = run_dir / "cases" / tool
        output = case_dir / "run" / f"{tool}.fa"
        output.parent.mkdir(parents=True)
        output.write_text(">c\nAAAA\n", encoding="utf-8")
        (case_dir / "wdl").mkdir(parents=True)
        (case_dir / "wdl" / "inputs.json").write_text("{}", encoding="utf-8")
        _write_json(case_dir / "manifest.json", {"dataset_key": "long-read-canu-pacbio-real-tests"})
        _write_json(
            case_dir / "result_manifest.json",
            {
                "status": "completed",
                "outputs": {
                    "primary": {
                        "path": str(output),
                        "exists": True,
                        "size_bytes": 6,
                    }
                },
            },
        )
        _write_json(
            case_dir / "analysis.json",
            {
                "status": "completed",
                "metrics": {},
                "checks": {"contigs_present": True},
            },
        )
        _write_worker(
            run_dir,
            tool,
            {"status": "completed", "summary": f"{tool} completed"},
        )

    result = evaluate_supervisor_run(run_dir)

    assert result.task_family == "benchmark"
    assert result.completion_status == "partial"
    assert result.completion_level == "B7.multi_operator_completed"
    assert result.completed_operators == ["Flye", "canu"]
    assert result.dataset_consistency == "same_dataset"
    assert result.comparison_valid is False
    assert result.false_positive is False


def test_evaluate_benchmark_flye_style_artifacts_count_as_completed(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-benchmark-flye-style"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "final_decision.json", {"task_type": "benchmark", "decision": "stop"})
    _write_json(
        run_dir / "operator_selection.json",
        {"selected_tools": ["Flye"], "dataset_key": "long-read-canu-pacbio-real-tests"},
    )
    _write_json(
        run_dir / "dataset_resolution.json",
        {"repo_to_dataset": {"Flye": "long-read-canu-pacbio-real-tests"}},
    )
    case_dir = run_dir / "cases" / "Flye"
    output = case_dir / "run" / "flye" / "assembly.fasta"
    output.parent.mkdir(parents=True)
    output.write_text(">c\nAAAA\n", encoding="utf-8")
    (case_dir / "wdl").mkdir(parents=True)
    (case_dir / "wdl" / "inputs.json").write_text("{}", encoding="utf-8")
    _write_json(case_dir / "manifest.json", {"dataset_key": "long-read-canu-pacbio-real-tests"})
    _write_json(
        case_dir / "result_manifest.json",
        {
            "status": "completed",
            "exit_code": 0,
            "file_checks": {"assembly": {"exists": True, "size_bytes": 6}},
            "outputs": {"assembly": str(output)},
        },
    )
    _write_json(
        case_dir / "analysis.json",
        {
            "status": "completed",
            "metrics": {},
            "output_presence": {"assembly": True},
            "output_sizes_bytes": {"assembly": 6},
        },
    )
    _write_worker(
        run_dir,
        "Flye",
        {"status": "completed", "summary": "Flye completed"},
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.task_family == "benchmark"
    assert result.completed_operators == ["Flye"]
    assert result.completion_level == "B6.single_operator_completed"
    assert result.false_positive is False


def test_evaluate_generic_run_summarizes_trace_for_harness(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-generic"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "request.json", {"task": "先给我一个口头判断"})
    _write_json(run_dir / "task_classification.json", {"task_type": "generic"})
    _write_json(
        run_dir / "final_decision.json",
        {"task_type": "generic", "decision": "stop"},
    )
    _write_json(
        run_dir / "graph_round_1.json",
        {
            "graph_id": "generic-r1",
            "round_index": 1,
            "nodes": [{"node_id": "init_generic"}],
            "edges": [],
        },
    )
    _write_json(
        run_dir / "graph_round_2.json",
        {
            "graph_id": "generic-r2",
            "round_index": 2,
            "nodes": [
                {"node_id": "inspect_sources"},
                {"node_id": "summarize"},
            ],
            "edges": [{"source": "inspect_sources", "target": "summarize"}],
        },
    )
    _write_worker(
        run_dir,
        "init_generic",
        {"status": "completed", "summary": "planned graph"},
    )
    _write_worker(
        run_dir,
        "inspect_sources",
        {
            "status": "completed",
            "summary": "checked source https://example.org/source",
            "evidence": ["https://example.org/source"],
        },
    )
    _write_worker(
        run_dir,
        "summarize",
        {"status": "completed", "summary": "answer keeps evidence boundary"},
    )
    (run_dir / "final_response.md").write_text(
        "口头判断：可以。证据边界：只基于本次 trace。\n\n判断轨迹（可审计摘要）\n- checked artifacts",
        encoding="utf-8",
    )
    _append_jsonl(
        run_dir / "tool_activity.jsonl",
        [
            {"event": "node_started", "node_id": "inspect_sources"},
            {"event": "worker_tool_call", "node_id": "inspect_sources", "tool_name": "web_search"},
            {"event": "worker_tool_result", "node_id": "inspect_sources", "tool_name": "web_search"},
            {"event": "worker_tool_call", "node_id": "inspect_sources", "tool_name": "fetch_url"},
            {"event": "worker_tool_result", "node_id": "inspect_sources", "tool_name": "fetch_url"},
            {"event": "node_finished", "node_id": "inspect_sources", "status": "completed"},
        ],
    )
    for node_id in ("init_generic", "inspect_sources", "summarize"):
        _append_jsonl(
            run_dir / "raw_worker_traces" / f"{node_id}.jsonl",
            [
                {"event": "worker_message", "node_id": node_id, "message": {"content": "hello"}},
                {
                    "event": "worker_invocation_finished",
                    "node_id": node_id,
                    "raw_output": '{"status":"completed","summary":"ok"}',
                    "source_urls": ["https://example.org/source"] if node_id == "inspect_sources" else [],
                },
                {
                    "event": "node_finished",
                    "node_id": node_id,
                    "status": "completed",
                    "duration_seconds": 1.5,
                },
            ],
        )

    result = write_evaluation_for_run(run_dir)

    assert result.task_family == "generic"
    assert result.completion_status == "completed"
    assert result.completion_level == "D6.evidence_boundary_preserved"
    assert result.generic_metrics["graph_shape_label"] == "evidence_then_synthesis"
    assert result.generic_metrics["source_url_count"] == 1
    assert result.generic_scores["traceability_score"] == 100
    assert "Generic trace is complete enough for harness comparison." in result.generic_findings
    summary_payload = json.loads((run_dir / "generic_trace_summary.json").read_text(encoding="utf-8"))
    assert summary_payload["scores"]["routing_score"] == 100
    assert summary_payload["metrics"]["raw_trace_file_count"] == 3


def test_evaluate_generic_run_flags_trace_quality_gaps(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "orchestration_runs" / "run-generic-gaps"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "task_classification.json", {"task_type": "generic"})
    _write_json(run_dir / "final_decision.json", {"task_type": "generic", "decision": "stop"})
    _write_json(
        run_dir / "graph_round_1.json",
        {
            "graph_id": "generic-r1",
            "round_index": 1,
            "nodes": [{"node_id": "answer"}],
            "edges": [],
        },
    )
    _write_worker(run_dir, "answer", {"status": "completed", "summary": "done"})
    (run_dir / "final_response.md").write_text("简短回答。", encoding="utf-8")
    _append_jsonl(
        run_dir / "tool_activity.jsonl",
        [{"event": "worker_tool_call", "node_id": "answer", "tool_name": "unknown"}],
    )

    result = evaluate_supervisor_run(run_dir)

    assert result.completion_status == "partial"
    assert result.completion_level == "D5.final_answer_written"
    assert "normalized tool names for all worker tool activity events" in result.required_evidence_missing
    assert "raw trace file for every executed worker node" in result.required_evidence_missing
    assert result.generic_scores["traceability_score"] < 100
