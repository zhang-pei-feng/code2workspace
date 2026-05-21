"""Artifact-based evaluation for supervisor orchestration runs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


GITHUB_LEVELS = {
    0: "G0.repo_not_materialized",
    1: "G1.repo_materialized",
    2: "G2.repo_inspected",
    3: "G3.environment_created",
    4: "G4.environment_built",
    5: "G5.workflow_created",
    6: "G6.workflow_validated",
    7: "G7.smoke_run_succeeded",
    8: "G8.workspace_reproducible",
}

BENCHMARK_LEVELS = {
    0: "B0.benchmark_not_registered",
    1: "B1.task_registered",
    2: "B2.operators_selected",
    3: "B3.inputs_resolved",
    4: "B4.cases_materialized",
    5: "B5.execution_started",
    6: "B6.single_operator_completed",
    7: "B7.multi_operator_completed",
    8: "B8.metrics_extracted",
    9: "B9.comparison_valid",
    10: "B10.result_reusable",
}

GENERIC_LEVELS = {
    0: "D0.no_generic_artifacts",
    1: "D1.classified_generic",
    2: "D2.graph_planned",
    3: "D3.nodes_executed",
    4: "D4.worker_trace_available",
    5: "D5.final_answer_written",
    6: "D6.evidence_boundary_preserved",
}


@dataclass(slots=True)
class EvaluationResult:
    task_family: str
    completion_status: str
    completion_level: str
    false_positive: bool = False
    unsupported_claims: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    required_evidence_missing: list[str] = field(default_factory=list)
    failure_stage: str | None = None
    failure_reason: str | None = None
    reproducible: bool = False
    selected_operators: list[str] = field(default_factory=list)
    completed_operators: list[str] = field(default_factory=list)
    failed_operators: list[str] = field(default_factory=list)
    dataset_consistency: str | None = None
    comparison_valid: bool | None = None
    history_reuse: bool = False
    generic_scores: dict[str, int] = field(default_factory=dict)
    generic_metrics: dict[str, object] = field(default_factory=dict)
    generic_findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "task_family": self.task_family,
            "completion_status": self.completion_status,
            "completion_level": self.completion_level,
            "false_positive": self.false_positive,
            "unsupported_claims": self.unsupported_claims,
            "evidence_paths": self.evidence_paths,
            "required_evidence_missing": self.required_evidence_missing,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "reproducible": self.reproducible,
        }
        if self.task_family == "benchmark":
            payload.update(
                {
                    "selected_operators": self.selected_operators,
                    "completed_operators": self.completed_operators,
                    "failed_operators": self.failed_operators,
                    "dataset_consistency": self.dataset_consistency,
                    "comparison_valid": self.comparison_valid,
                    "history_reuse": self.history_reuse,
                }
            )
        if self.task_family == "generic":
            payload.update(
                {
                    "generic_scores": self.generic_scores,
                    "generic_metrics": self.generic_metrics,
                    "generic_findings": self.generic_findings,
                }
            )
        return payload


def write_evaluation_for_run(run_dir: Path) -> EvaluationResult:
    """Evaluate a supervisor run and write ``evaluation.json``."""
    result = evaluate_supervisor_run(run_dir)
    (run_dir / "evaluation.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if result.task_family == "generic":
        (run_dir / "generic_trace_summary.json").write_text(
            json.dumps(
                {
                    "task_family": result.task_family,
                    "completion_status": result.completion_status,
                    "completion_level": result.completion_level,
                    "metrics": result.generic_metrics,
                    "scores": result.generic_scores,
                    "findings": result.generic_findings,
                    "required_evidence_missing": result.required_evidence_missing,
                    "evidence_paths": result.evidence_paths,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return result


def evaluate_supervisor_run(run_dir: Path) -> EvaluationResult:
    task_family = _task_family(run_dir)
    if task_family == "github2workspace":
        return evaluate_github2workspace_run(run_dir)
    if task_family == "benchmark":
        return evaluate_benchmark_run(run_dir)
    if task_family == "generic":
        return evaluate_generic_run(run_dir)
    return EvaluationResult(
        task_family=task_family,
        completion_status="invalid",
        completion_level="unsupported_task_family",
        required_evidence_missing=["github2workspace_or_benchmark_artifacts"],
        failure_stage="task_classification",
        failure_reason=f"unsupported_task_family:{task_family}",
    )


def evaluate_github2workspace_run(run_dir: Path) -> EvaluationResult:
    evidence: list[Path] = []
    required_missing: list[str] = []
    level = 0

    materialization = _read_json(run_dir / "github_repo_materialization.json")
    if _github_materialized(materialization):
        level = max(level, 1)
        evidence.append(run_dir / "github_repo_materialization.json")

    inspect = _worker_result(run_dir, "inspect")
    if _status_in(inspect, {"completed", "partial"}):
        level = max(level, 2)
        evidence.append(run_dir / "worker_outputs" / "inspect.json")

    build = _worker_result(run_dir, "build")
    build_text = _result_text(build)
    build_artifacts = _result_artifact_paths(build)
    if build_artifacts and any(path.name == "Dockerfile" for path in build_artifacts):
        level = max(level, 3)
        evidence.append(run_dir / "worker_outputs" / "build.json")
    if _status_in(build, {"completed", "partial"}) and _has_success_marker(
        build_text,
        ("docker image build succeeded", "docker build completed", "build succeeded"),
    ):
        level = max(level, 4)
        evidence.append(run_dir / "worker_outputs" / "build.json")

    wdl = _worker_result(run_dir, "wdl") or _worker_result(run_dir, "retry_wdl")
    wdl_artifacts = _result_artifact_paths(wdl)
    discovered_wdl = list(run_dir.glob("**/*.wdl")) + [
        path for path in build_artifacts if path.suffix == ".wdl"
    ]
    if _status_in(wdl, {"completed", "partial"}) or wdl_artifacts or discovered_wdl:
        if wdl_artifacts or discovered_wdl:
            level = max(level, 5)
        if _status_in(wdl, {"completed", "partial"}):
            level = max(level, 6)
            evidence.append(run_dir / "worker_outputs" / "wdl.json")

    smoke_outputs, smoke_log = _successful_smoke_paths(run_dir)
    if smoke_outputs is not None:
        level = max(level, 7)
        evidence.extend([smoke_outputs, smoke_log] if smoke_log else [smoke_outputs])

    reproducible = _github_reproducible(run_dir, level=level, smoke_outputs=smoke_outputs, smoke_log=smoke_log)
    if reproducible:
        level = max(level, 8)

    missing_by_level = {
        1: "github_repo_materialization.json with a successful materialization strategy",
        2: "worker_outputs/inspect.json with completed or partial status",
        4: "worker_outputs/build.json with Docker build success evidence",
        5: "a generated WDL artifact",
        7: "wdl_smoke_run/*/outputs.json plus successful workflow.log",
    }
    for threshold, label in missing_by_level.items():
        if level < threshold:
            required_missing.append(label)

    unsupported = _github_unsupported_claims(run_dir, level)
    failed_node = _first_failed_worker(run_dir, ["inspect", "build", "wdl", "retry_wdl", "summarize"])
    status = "completed" if level >= 7 else "partial" if level > 0 else "failed"
    failure_stage, failure_reason = _github_failure(level, failed_node)
    return EvaluationResult(
        task_family="github2workspace",
        completion_status=status,
        completion_level=GITHUB_LEVELS[level],
        false_positive=bool(unsupported),
        unsupported_claims=unsupported,
        evidence_paths=_stringify_paths(evidence),
        required_evidence_missing=required_missing,
        failure_stage=failure_stage,
        failure_reason=failure_reason,
        reproducible=reproducible,
    )


def evaluate_benchmark_run(run_dir: Path) -> EvaluationResult:
    evidence: list[Path] = []
    required_missing: list[str] = []
    level = 0

    selection = _read_json(run_dir / "operator_selection.json")
    selected_tools = _selected_benchmark_tools(run_dir, selection)
    cases_root = run_dir / "cases"
    case_dirs = [cases_root / tool for tool in selected_tools] if selected_tools else []
    if selection or _status_in(_worker_result(run_dir, "register"), {"completed", "partial"}):
        level = max(level, 1)
        evidence.append(run_dir / "operator_selection.json")
    if selected_tools:
        level = max(level, 2)
    if _benchmark_inputs_resolved(run_dir, case_dirs):
        level = max(level, 3)
        evidence.extend([path / "wdl" / "inputs.json" for path in case_dirs if (path / "wdl" / "inputs.json").exists()])
    if _benchmark_cases_materialized(case_dirs):
        level = max(level, 4)
        evidence.extend([path / "manifest.json" for path in case_dirs if (path / "manifest.json").exists()])

    completed: list[str] = []
    failed: list[str] = []
    execution_started = False
    metrics_extracted = False
    history_reuse = False
    for tool, case_dir in zip(selected_tools, case_dirs, strict=False):
        run_status = _read_json(case_dir / "run" / "status.json")
        wdl_status = _read_json(case_dir / "wdl" / "status.json")
        worker_result = _worker_result(run_dir, tool)
        analysis_path = case_dir / "analysis.json"
        result_manifest_path = _benchmark_result_manifest_path(case_dir)
        if _benchmark_case_execution_started(
            case_dir=case_dir,
            run_status=run_status,
            wdl_status=wdl_status,
            worker_result=worker_result,
        ):
            execution_started = True
            evidence.extend(
                path
                for path in (
                    case_dir / "run" / "status.json",
                    case_dir / "wdl" / "status.json",
                    analysis_path,
                    result_manifest_path,
                    run_dir / "worker_outputs" / f"{tool}.json",
                )
                if path.exists()
            )
        if _benchmark_case_success(
            case_dir=case_dir,
            run_status=run_status,
            wdl_status=wdl_status,
            worker_result=worker_result,
        ):
            completed.append(tool)
        elif run_status or wdl_status or str(worker_result.get("status", "")).strip() in {"failed", "blocked"}:
            failed.append(tool)
        analysis = _read_json(analysis_path)
        if isinstance(analysis.get("metrics"), dict) and analysis["metrics"]:
            metrics_extracted = True
            evidence.append(analysis_path)
        if (case_dir / "run" / "reused_result_record.json").exists():
            history_reuse = True
            evidence.append(case_dir / "run" / "reused_result_record.json")

    if execution_started:
        level = max(level, 5)
    if completed:
        level = max(level, 6)
    if len(completed) >= 2:
        level = max(level, 7)
    if metrics_extracted:
        level = max(level, 8)

    dataset_consistency = _dataset_consistency(run_dir, selected_tools, case_dirs)
    summary = _read_json(run_dir / "benchmark_supervisor_summary.json")
    comparison_valid = (
        len(completed) >= 2
        and metrics_extracted
        and dataset_consistency in {"same_dataset", "explicitly_comparable"}
        and isinstance(summary.get("comparison"), dict)
        and bool(summary.get("comparison"))
    )
    if comparison_valid:
        level = max(level, 9)
        evidence.append(run_dir / "benchmark_supervisor_summary.json")
    if history_reuse or _has_benchmark_result_record(run_dir, selected_tools):
        level = max(level, 10)

    missing_by_level = {
        1: "operator_selection.json or completed register worker output",
        2: "selected benchmark operators",
        3: "resolved benchmark inputs",
        4: "materialized case manifests and WDL/input assets",
        6: "at least one successful operator run",
        8: "analysis metrics for at least one completed operator",
        9: "valid multi-operator comparison on comparable inputs",
    }
    for threshold, label in missing_by_level.items():
        if level < threshold:
            required_missing.append(label)

    unsupported = _benchmark_unsupported_claims(
        run_dir,
        level=level,
        completed=completed,
        comparison_valid=comparison_valid,
    )
    failed_node = _first_failed_worker(run_dir, ["register", *[f"run_{tool}" for tool in selected_tools], "summarize"])
    status = "completed" if level >= 9 else "partial" if level > 0 else "failed"
    failure_stage, failure_reason = _benchmark_failure(level, failed_node, completed, failed)
    return EvaluationResult(
        task_family="benchmark",
        completion_status=status,
        completion_level=BENCHMARK_LEVELS[level],
        false_positive=bool(unsupported),
        unsupported_claims=unsupported,
        evidence_paths=_stringify_paths(evidence),
        required_evidence_missing=required_missing,
        failure_stage=failure_stage,
        failure_reason=failure_reason,
        reproducible=level >= 4,
        selected_operators=selected_tools,
        completed_operators=completed,
        failed_operators=failed,
        dataset_consistency=dataset_consistency,
        comparison_valid=comparison_valid,
        history_reuse=history_reuse,
    )


def evaluate_generic_run(run_dir: Path) -> EvaluationResult:
    """Summarize and score generic Supervisor Graph traces for harness optimization."""

    metrics = _generic_trace_metrics(run_dir)
    evidence: list[Path] = []
    for relative in (
        "request.json",
        "task_classification.json",
        "final_decision.json",
        "final_response.md",
        "tool_activity.jsonl",
    ):
        path = run_dir / relative
        if path.exists():
            evidence.append(path)
    evidence.extend(sorted((run_dir / "node_traces").glob("*.json")))
    evidence.extend(sorted((run_dir / "raw_worker_traces").glob("*.jsonl")))

    level = 0
    if metrics["classified_generic"]:
        level = max(level, 1)
    if metrics["round_count"] > 0 and metrics["node_count"] > 0:
        level = max(level, 2)
    if metrics["executed_node_count"] > 0:
        level = max(level, 3)
    if metrics["raw_trace_file_count"] > 0 or metrics["tool_event_count"] > 0:
        level = max(level, 4)
    if metrics["final_answer_length"] > 0:
        level = max(level, 5)
    if metrics["has_evidence_boundary"] or metrics["has_audit_summary"]:
        level = max(level, 6)

    required_missing = _generic_required_missing(metrics, level)
    scores = _generic_scores(metrics)
    findings = _generic_findings(metrics, scores)
    failed_nodes = metrics["failed_nodes"]
    blocked_nodes = metrics["blocked_nodes"]
    partial_nodes = metrics["partial_nodes"]
    if failed_nodes:
        status = "failed"
    elif required_missing or blocked_nodes or partial_nodes:
        status = "partial"
    else:
        status = "completed"
    failure_stage, failure_reason = _generic_failure(metrics, required_missing)

    return EvaluationResult(
        task_family="generic",
        completion_status=status,
        completion_level=GENERIC_LEVELS[level],
        false_positive=False,
        evidence_paths=_stringify_paths(evidence),
        required_evidence_missing=required_missing,
        failure_stage=failure_stage,
        failure_reason=failure_reason,
        reproducible=level >= 5 and metrics["raw_trace_file_count"] > 0,
        generic_scores=scores,
        generic_metrics=metrics,
        generic_findings=findings,
    )


def _task_family(run_dir: Path) -> str:
    decision = _read_json(run_dir / "final_decision.json")
    task_type = str(decision.get("task_type", "")).strip()
    if task_type:
        return task_type
    classification = _read_json(run_dir / "task_classification.json")
    return str(classification.get("task_type", "generic")).strip() or "generic"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _worker_result(run_dir: Path, node_id: str) -> dict[str, Any]:
    payload = _read_json(run_dir / "worker_outputs" / f"{node_id}.json")
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _status_in(result: dict[str, Any], statuses: set[str]) -> bool:
    return str(result.get("status", "")).strip() in statuses


def _result_text(result: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("summary", "failure_reason", "next_action_hint"):
        value = result.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("evidence", "artifacts"):
        value = result.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
    return "\n".join(values).casefold()


def _result_artifact_paths(result: dict[str, Any]) -> list[Path]:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    paths: list[Path] = []
    for artifact in artifacts:
        if isinstance(artifact, str) and artifact.strip():
            paths.append(Path(artifact))
    return paths


def _has_success_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _github_materialized(payload: dict[str, Any]) -> bool:
    if not payload:
        return False
    if str(payload.get("selected_strategy", "")).strip():
        return True
    attempts = payload.get("attempts")
    return isinstance(attempts, list) and any(
        isinstance(item, dict) and item.get("status") == "success" for item in attempts
    )


def _successful_smoke_paths(run_dir: Path) -> tuple[Path | None, Path | None]:
    smoke_root = run_dir / "wdl_smoke_run"
    if not smoke_root.exists():
        return None, None
    candidates = sorted(smoke_root.glob("*/outputs.json"), key=lambda path: path.stat().st_mtime)
    for outputs_path in reversed(candidates):
        outputs = _read_json(outputs_path)
        if not outputs:
            continue
        workflow_log = outputs_path.parent / "workflow.log"
        log_text = _read_text(workflow_log).casefold()
        if "exit_code: 0" in log_text or "succeeded" in log_text:
            return outputs_path, workflow_log if workflow_log.exists() else None
    return None, None


def _github_reproducible(
    run_dir: Path,
    *,
    level: int,
    smoke_outputs: Path | None,
    smoke_log: Path | None,
) -> bool:
    if level < 7 or smoke_outputs is None:
        return False
    required = [run_dir / "request.json", run_dir / "final_decision.json", smoke_outputs]
    if smoke_log is not None:
        required.append(smoke_log)
    return all(path.exists() for path in required)


def _github_unsupported_claims(run_dir: Path, level: int) -> list[str]:
    text = _read_text(run_dir / "final_response.md").casefold()
    claims: list[str] = []
    if not text:
        return claims
    if level < 4 and _contains_any(text, ("docker build succeeded", "docker 镜像构建成功", "镜像构建成功")):
        claims.append("final response claims Docker build success without build-success evidence")
    if level < 7 and (
        (_contains_any(text, ("端到端", "end-to-end")) and _contains_any(text, ("成功", "succeeded", "跑通")))
        or _contains_any(text, ("smoke run succeeded", "workflow succeeded", "wdl smoke 成功"))
    ):
        claims.append("final response claims workflow/smoke success without successful smoke-run evidence")
    if level < 8 and _contains_any(text, ("完全可复现", "fully reproducible", "完整可复现")):
        claims.append("final response claims full reproducibility without reproducibility evidence")
    return claims


def _benchmark_unsupported_claims(
    run_dir: Path,
    *,
    level: int,
    completed: list[str],
    comparison_valid: bool,
) -> list[str]:
    text = _read_text(run_dir / "final_response.md").casefold()
    claims: list[str] = []
    if not text:
        return claims
    if level < 6 and _contains_any(text, ("benchmark completed", "基准测试已完成", "运行完成")):
        claims.append("final response claims benchmark completion without a successful operator run")
    if len(completed) < 2 and _contains_any(
        text,
        ("多工具比较", "multi-tool comparison", "工具比较", "两个工具", "多个工具"),
    ):
        claims.append("final response claims multi-operator comparison with fewer than two completed operators")
    if (
        not comparison_valid
        and _contains_any(text, ("公平比较", "fair comparison", "comparison is valid", "比较有效"))
        and not _benchmark_execution_only_comparison_claim(text)
    ):
        claims.append("final response claims a valid/fair comparison without comparable multi-operator evidence")
    return claims


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _benchmark_execution_only_comparison_claim(text: str) -> bool:
    """Allow scoped fairness claims limited to shared-input run success."""
    success_scope = _contains_any(
        text,
        (
            "能否跑通",
            "是否跑通",
            "都跑通",
            "who ran successfully",
            "both succeeded",
            "both ran successfully",
            "same dataset",
            "同一数据集",
            "同一份共享",
        ),
    )
    no_winner_scope = _contains_any(
        text,
        (
            "不能下更优结论",
            "不能判断谁更优",
            "不能负责任地下更强结论",
            "暂时不能下",
            "can't determine which is better",
            "cannot determine which is better",
            "cannot conclude which is better",
            "no stronger conclusion",
        ),
    )
    return success_scope and no_winner_scope


def _first_failed_worker(run_dir: Path, node_order: list[str]) -> dict[str, Any] | None:
    for node_id in node_order:
        result = _worker_result(run_dir, node_id)
        if str(result.get("status", "")) == "failed":
            return {"node_id": node_id, **result}
    return None


def _github_failure(level: int, failed_node: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if failed_node:
        return str(failed_node["node_id"]), _optional_str(failed_node.get("failure_reason")) or "node_failed"
    if level >= 7:
        return None, None
    stages = {
        0: ("repo_materialization", "repository was not materialized"),
        1: ("inspect", "repository was materialized but not inspected"),
        2: ("build", "repository was inspected but environment was not created"),
        3: ("build", "environment was created but build success was not verified"),
        4: ("wdl", "environment was built but workflow was not created"),
        5: ("wdl", "workflow was created but validation was not verified"),
        6: ("smoke_run", "workflow validation did not reach a successful smoke run"),
    }
    return stages.get(level, (None, None))


def _benchmark_failure(
    level: int,
    failed_node: dict[str, Any] | None,
    completed: list[str],
    failed: list[str],
) -> tuple[str | None, str | None]:
    if level >= 9:
        return None, None
    if failed_node:
        return str(failed_node["node_id"]), _optional_str(failed_node.get("failure_reason")) or "node_failed"
    if failed:
        return "operator_execution", f"failed operators: {', '.join(failed)}"
    if completed and level < 9:
        return "comparison", "completed operators are insufficient for a valid comparison"
    stages = {
        0: ("register", "benchmark was not registered"),
        1: ("operator_selection", "no operators were selected"),
        2: ("input_resolution", "selected operators do not have resolved inputs"),
        3: ("case_materialization", "benchmark cases were not fully materialized"),
        4: ("operator_execution", "execution did not start"),
        5: ("operator_execution", "no operator completed successfully"),
        6: ("operator_execution", "only one operator completed successfully"),
        7: ("metrics", "multi-operator run completed without extracted metrics"),
        8: ("comparison", "metrics exist but no valid comparable summary was produced"),
    }
    return stages.get(level, (None, None))


def _selected_benchmark_tools(run_dir: Path, selection: dict[str, Any]) -> list[str]:
    tools = selection.get("selected_tools")
    if isinstance(tools, list):
        selected = [str(item) for item in tools if isinstance(item, str) and item.strip()]
        if selected:
            return selected
    cases_root = run_dir / "cases"
    if cases_root.exists():
        return sorted(path.name for path in cases_root.iterdir() if path.is_dir())
    return []


def _benchmark_inputs_resolved(run_dir: Path, case_dirs: list[Path]) -> bool:
    if (run_dir / "dataset_resolution.json").exists():
        return True
    return any((case_dir / "wdl" / "inputs.json").exists() for case_dir in case_dirs)


def _benchmark_cases_materialized(case_dirs: list[Path]) -> bool:
    if not case_dirs:
        return False
    for case_dir in case_dirs:
        if not (case_dir / "manifest.json").exists():
            return False
        if not ((case_dir / "wdl" / "workflow.wdl").exists() or (case_dir / "wdl" / "inputs.json").exists()):
            return False
    return True


def _benchmark_case_success(
    *,
    case_dir: Path,
    run_status: dict[str, Any],
    wdl_status: dict[str, Any],
    worker_result: dict[str, Any],
) -> bool:
    result_manifest = _read_json(_benchmark_result_manifest_path(case_dir))
    analysis = _read_json(case_dir / "analysis.json")
    success_markers = [
        run_status.get("success") is True,
        wdl_status.get("success") is True,
        str(worker_result.get("status", "")).strip() == "completed",
        str(result_manifest.get("status", "")).strip() == "completed",
        result_manifest.get("exit_code") == 0,
        (
            isinstance(result_manifest.get("workflow"), dict)
            and result_manifest["workflow"].get("exit_code") == 0
        ),
        str(analysis.get("status", "")).strip() == "completed",
    ]
    if not any(success_markers):
        return False
    if _benchmark_manifest_has_output_evidence(result_manifest):
        return True
    if _benchmark_analysis_has_output_evidence(analysis):
        return True
    if isinstance(run_status.get("output_artifacts"), list) and run_status["output_artifacts"]:
        return True
    if isinstance(wdl_status.get("output_artifacts"), list) and wdl_status["output_artifacts"]:
        return True
    return run_status.get("success") is True


def _benchmark_case_execution_started(
    *,
    case_dir: Path,
    run_status: dict[str, Any],
    wdl_status: dict[str, Any],
    worker_result: dict[str, Any],
) -> bool:
    if run_status or wdl_status or worker_result:
        return True
    if (case_dir / "analysis.json").exists():
        return True
    return _benchmark_result_manifest_path(case_dir).exists()


def _benchmark_result_manifest_path(case_dir: Path) -> Path:
    for path in (
        case_dir / "run" / "result_manifest.json",
        case_dir / "result_manifest.json",
    ):
        if path.exists():
            return path
    return case_dir / "run" / "result_manifest.json"


def _benchmark_manifest_has_output_evidence(result_manifest: dict[str, Any]) -> bool:
    expected_outputs = result_manifest.get("expected_outputs")
    if isinstance(expected_outputs, dict) and expected_outputs:
        if any(
            isinstance(item, dict) and item.get("exists") is True
            for item in expected_outputs.values()
        ):
            return True
    output_checks = result_manifest.get("output_checks")
    if isinstance(output_checks, dict) and output_checks:
        if any(
            isinstance(item, dict)
            and (
                item.get("exists") is True
                or item.get("present") is True
                or int(item.get("size_bytes", 0) or 0) > 0
            )
            for item in output_checks.values()
        ):
            return True
    file_checks = result_manifest.get("file_checks")
    if isinstance(file_checks, dict) and file_checks:
        if any(
            isinstance(item, dict)
            and (
                item.get("exists") is True
                or item.get("present") is True
                or int(item.get("size_bytes", 0) or 0) > 0
            )
            for item in file_checks.values()
        ):
            return True
    outputs = result_manifest.get("outputs")
    if isinstance(outputs, dict) and outputs:
        if any(
            (
                isinstance(item, dict)
                and (
                    item.get("exists") is True
                    or item.get("present") is True
                    or int(item.get("size_bytes", 0) or 0) > 0
                )
            )
            or (isinstance(item, str) and bool(item.strip()))
            for item in outputs.values()
        ):
            return True
    return False


def _benchmark_analysis_has_output_evidence(analysis: dict[str, Any]) -> bool:
    output_checks = analysis.get("output_checks")
    if isinstance(output_checks, dict) and output_checks:
        if any(
            isinstance(item, dict)
            and (
                item.get("exists") is True
                or item.get("present") is True
                or int(item.get("size_bytes", 0) or 0) > 0
            )
            for item in output_checks.values()
        ):
            return True
    output_presence = analysis.get("output_presence")
    if isinstance(output_presence, dict) and output_presence:
        if any(value is True for value in output_presence.values()):
            return True
    output_sizes = analysis.get("output_sizes_bytes")
    if isinstance(output_sizes, dict) and output_sizes:
        if any(int(value or 0) > 0 for value in output_sizes.values()):
            return True
    checks = analysis.get("checks")
    if isinstance(checks, dict):
        if any(
            key.endswith("_present") and value is True
            for key, value in checks.items()
        ):
            return True
    return analysis.get("real_contigs_fasta_present") is True


def _dataset_consistency(run_dir: Path, selected_tools: list[str], case_dirs: list[Path]) -> str:
    datasets: list[str] = []
    resolution = _read_json(run_dir / "dataset_resolution.json")
    repo_to_dataset = resolution.get("repo_to_dataset")
    if isinstance(repo_to_dataset, dict):
        datasets.extend(
            str(repo_to_dataset.get(tool, "")).strip()
            for tool in selected_tools
            if str(repo_to_dataset.get(tool, "")).strip()
        )
    if not datasets:
        for case_dir in case_dirs:
            manifest = _read_json(case_dir / "manifest.json")
            dataset = str(manifest.get("dataset_key", "")).strip()
            if dataset:
                datasets.append(dataset)
    if not datasets:
        return "unknown"
    unique = sorted(set(datasets))
    if len(unique) == 1 and len(datasets) >= len(selected_tools):
        return "same_dataset"
    if len(unique) == 1:
        return "single_dataset_partial_mapping"
    return "mixed_or_unverified"


def _has_benchmark_result_record(run_dir: Path, selected_tools: list[str]) -> bool:
    run_id = run_dir.name
    for store_root in (run_dir.parent.parent / "benchmark_comparison_history_store",):
        if not store_root.exists():
            continue
        for tool in selected_tools:
            if list((store_root / "records" / _safe_part(tool) / _safe_part(run_id)).glob("benchmark_result_record.json")):
                return True
    return False


def _generic_trace_metrics(run_dir: Path) -> dict[str, Any]:
    classification = _read_json(run_dir / "task_classification.json")
    final_decision = _read_json(run_dir / "final_decision.json")
    final_response = _read_text(run_dir / "final_response.md")
    graph_paths = sorted(run_dir.glob("graph_round_*.json"))
    graphs = [_read_json(path) for path in graph_paths]
    graph_nodes: list[dict[str, Any]] = []
    edge_count = 0
    graph_shapes: list[dict[str, object]] = []
    for graph in graphs:
        nodes = graph.get("nodes")
        edges = graph.get("edges")
        node_ids: list[str] = []
        if isinstance(nodes, list):
            graph_nodes.extend(node for node in nodes if isinstance(node, dict))
            node_ids = [
                str(node.get("node_id", "")).strip()
                for node in nodes
                if isinstance(node, dict) and str(node.get("node_id", "")).strip()
            ]
        if isinstance(edges, list):
            edge_count += len(edges)
        graph_shapes.append(
            {
                "round_index": graph.get("round_index"),
                "graph_id": graph.get("graph_id"),
                "node_ids": node_ids,
                "edge_count": len(edges) if isinstance(edges, list) else 0,
            }
        )

    worker_results: dict[str, dict[str, Any]] = {}
    for path in sorted((run_dir / "worker_outputs").glob("*.json")):
        payload = _read_json(path)
        result = payload.get("result")
        if isinstance(result, dict):
            worker_results[path.stem] = result
    status_counts: dict[str, int] = {}
    failed_nodes: list[str] = []
    blocked_nodes: list[str] = []
    partial_nodes: list[str] = []
    for node_id, result in worker_results.items():
        status = str(result.get("status", "")).strip() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "failed":
            failed_nodes.append(node_id)
        elif status == "blocked":
            blocked_nodes.append(node_id)
        elif status == "partial":
            partial_nodes.append(node_id)

    tool_counts, unknown_tool_events = _generic_tool_activity_metrics(run_dir / "tool_activity.jsonl")
    raw_metrics = _generic_raw_trace_metrics(run_dir / "raw_worker_traces")
    source_urls = _dedupe_strings(
        [
            *raw_metrics["source_urls"],
            *_extract_urls(final_response),
            *_generic_urls_from_worker_results(worker_results),
        ]
    )
    has_fetch_after_search = bool(tool_counts.get("worker_tool_result", 0)) and _tool_activity_has_fetch_after_search(
        run_dir / "tool_activity.jsonl"
    )
    final_text = final_response.casefold()
    has_evidence_boundary = _contains_any(
        final_text,
        ("证据边界", "不确定", "局限", "uncertain", "uncertainty", "evidence gap", "直接", "推断"),
    )
    has_audit_summary = "判断轨迹" in final_response or "可审计摘要" in final_response
    message_count = int(raw_metrics["worker_message_count"])
    raw_trace_file_count = int(raw_metrics["raw_trace_file_count"])
    node_count = len(graph_nodes)
    executed_node_count = len(worker_results)
    duration_by_node = raw_metrics["duration_by_node"]
    total_duration_seconds = round(sum(duration_by_node.values()), 3)
    graph_shape_label = _generic_graph_shape_label(graph_shapes)
    return {
        "classified_generic": str(classification.get("task_type", "")).strip() == "generic"
        or str(final_decision.get("task_type", "")).strip() == "generic",
        "round_count": len(graph_paths),
        "node_count": node_count,
        "edge_count": edge_count,
        "executed_node_count": executed_node_count,
        "graph_shapes": graph_shapes,
        "graph_shape_label": graph_shape_label,
        "status_counts": status_counts,
        "failed_nodes": failed_nodes,
        "blocked_nodes": blocked_nodes,
        "partial_nodes": partial_nodes,
        "tool_event_counts": tool_counts,
        "tool_event_count": sum(tool_counts.values()),
        "unknown_tool_events": unknown_tool_events,
        "raw_trace_file_count": raw_trace_file_count,
        "raw_worker_message_count": message_count,
        "raw_output_record_count": raw_metrics["raw_output_record_count"],
        "duration_by_node": duration_by_node,
        "total_duration_seconds": total_duration_seconds,
        "source_url_count": len(source_urls),
        "source_urls": source_urls[:50],
        "has_fetch_after_search": has_fetch_after_search,
        "final_answer_length": len(final_response.strip()),
        "has_evidence_boundary": has_evidence_boundary,
        "has_audit_summary": has_audit_summary,
        "final_decision": str(final_decision.get("decision", "")).strip(),
    }


def _generic_tool_activity_metrics(path: Path) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    unknown_tool_events = 0
    for event in _read_jsonl(path):
        name = str(event.get("event", "")).strip() or "unknown"
        counts[name] = counts.get(name, 0) + 1
        if event.get("tool_name") == "unknown":
            unknown_tool_events += 1
    return counts, unknown_tool_events


def _generic_raw_trace_metrics(raw_trace_root: Path) -> dict[str, Any]:
    source_urls: list[str] = []
    duration_by_node: dict[str, float] = {}
    worker_message_count = 0
    raw_output_record_count = 0
    raw_files = sorted(raw_trace_root.glob("*.jsonl")) if raw_trace_root.exists() else []
    for path in raw_files:
        node_id = path.stem
        for event in _read_jsonl(path):
            if event.get("event") == "worker_message":
                worker_message_count += 1
            if event.get("raw_output"):
                raw_output_record_count += 1
            urls = event.get("source_urls")
            if isinstance(urls, list):
                source_urls.extend(str(item) for item in urls if isinstance(item, str))
            if event.get("event") == "node_finished":
                duration = event.get("duration_seconds")
                if isinstance(duration, int | float):
                    duration_by_node[node_id] = float(duration)
    return {
        "raw_trace_file_count": len(raw_files),
        "worker_message_count": worker_message_count,
        "raw_output_record_count": raw_output_record_count,
        "duration_by_node": duration_by_node,
        "source_urls": _dedupe_strings(source_urls),
    }


def _generic_urls_from_worker_results(worker_results: dict[str, dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for result in worker_results.values():
        urls.extend(_extract_urls(json.dumps(result, ensure_ascii=False, default=str)))
    return _dedupe_strings(urls)


def _tool_activity_has_fetch_after_search(path: Path) -> bool:
    saw_search = False
    for event in _read_jsonl(path):
        tool_name = str(event.get("tool_name", "")).casefold()
        if "search" in tool_name:
            saw_search = True
        if saw_search and ("fetch" in tool_name or "read" in tool_name):
            return True
    return False


def _generic_graph_shape_label(graph_shapes: list[dict[str, object]]) -> str:
    node_ids = [
        str(node_id)
        for shape in graph_shapes
        for node_id in shape.get("node_ids", [])
        if isinstance(shape.get("node_ids"), list)
    ]
    if not node_ids:
        return "missing_graph"
    if len(node_ids) <= 2:
        return "direct_or_minimal"
    if any("context" in node_id or "evidence" in node_id or "inspect" in node_id for node_id in node_ids):
        if any("compose" in node_id or "summarize" in node_id for node_id in node_ids):
            return "evidence_then_synthesis"
    if any("fix" in node_id or "repair" in node_id or "verify" in node_id for node_id in node_ids):
        return "inspect_fix_verify"
    return "multi_node_generic"


def _generic_required_missing(metrics: dict[str, Any], level: int) -> list[str]:
    missing: list[str] = []
    if level < 1:
        missing.append("task_classification.json or final_decision.json marking task_type=generic")
    if level < 2:
        missing.append("at least one graph_round_*.json with planned nodes")
    if level < 3:
        missing.append("worker_outputs/*.json for executed generic nodes")
    if level < 4:
        missing.append("raw_worker_traces/*.jsonl or tool_activity.jsonl")
    if level < 5:
        missing.append("final_response.md with a user-facing answer")
    if metrics["unknown_tool_events"]:
        missing.append("normalized tool names for all worker tool activity events")
    if metrics["raw_trace_file_count"] < metrics["executed_node_count"]:
        missing.append("raw trace file for every executed worker node")
    return missing


def _generic_scores(metrics: dict[str, Any]) -> dict[str, int]:
    routing = 100 if metrics["classified_generic"] else 0
    graph_fit = 40
    if metrics["round_count"] >= 1 and metrics["node_count"] >= 1:
        graph_fit = 70
    if metrics["graph_shape_label"] in {"evidence_then_synthesis", "inspect_fix_verify", "direct_or_minimal"}:
        graph_fit = 85
    if metrics["node_count"] > 8:
        graph_fit -= 15
    traceability = 0
    if metrics["executed_node_count"]:
        traceability += 25
    if metrics["raw_trace_file_count"] >= metrics["executed_node_count"] and metrics["executed_node_count"]:
        traceability += 35
    if metrics["raw_output_record_count"]:
        traceability += 20
    if metrics["duration_by_node"]:
        traceability += 10
    if metrics["tool_event_count"]:
        traceability += 10
    traceability = min(100, traceability)
    evidence = 40
    if metrics["source_url_count"]:
        evidence += 20
    if metrics["has_fetch_after_search"]:
        evidence += 20
    if metrics["has_evidence_boundary"]:
        evidence += 20
    answer = 40
    if metrics["final_answer_length"] > 0:
        answer += 30
    if metrics["has_audit_summary"]:
        answer += 20
    if metrics["has_evidence_boundary"]:
        answer += 10
    efficiency = 100
    if metrics["node_count"] > 6:
        efficiency -= 15
    if metrics["tool_event_count"] > 80:
        efficiency -= 15
    if metrics["total_duration_seconds"] > 300:
        efficiency -= 20
    return {
        "routing_score": max(0, min(100, routing)),
        "graph_fit_score": max(0, min(100, graph_fit)),
        "traceability_score": max(0, min(100, traceability)),
        "evidence_score": max(0, min(100, evidence)),
        "answer_score": max(0, min(100, answer)),
        "efficiency_score": max(0, min(100, efficiency)),
    }


def _generic_findings(metrics: dict[str, Any], scores: dict[str, int]) -> list[str]:
    findings: list[str] = []
    if not metrics["classified_generic"]:
        findings.append("Task was not classified as generic.")
    if metrics["node_count"] == 0:
        findings.append("No generic graph nodes were planned.")
    if metrics["raw_trace_file_count"] < metrics["executed_node_count"]:
        findings.append("Some executed nodes do not have raw worker trace files.")
    if metrics["unknown_tool_events"]:
        findings.append("tool_activity.jsonl contains worker tool events with unknown tool names.")
    if scores["efficiency_score"] < 80:
        findings.append("Trace suggests possible over-orchestration or high tool/runtime cost.")
    if metrics["source_url_count"] and not metrics["has_evidence_boundary"]:
        findings.append("Sources were collected, but final answer did not clearly preserve evidence boundaries.")
    if not findings:
        findings.append("Generic trace is complete enough for harness comparison.")
    return findings


def _generic_failure(
    metrics: dict[str, Any],
    required_missing: list[str],
) -> tuple[str | None, str | None]:
    if metrics["failed_nodes"]:
        return "worker_execution", f"failed nodes: {', '.join(metrics['failed_nodes'])}"
    if metrics["blocked_nodes"]:
        return "worker_execution", f"blocked nodes: {', '.join(metrics['blocked_nodes'])}"
    if not required_missing:
        return None, None
    first = required_missing[0]
    if "task_classification" in first:
        return "task_classification", first
    if "graph_round" in first:
        return "planning", first
    if "worker_outputs" in first or "raw trace" in first:
        return "worker_execution", first
    if "final_response" in first:
        return "final_response", first
    return "trace_quality", first


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _extract_urls(text: str) -> list[str]:
    candidates = re.findall(r"https?://[^\s<>)\"']+", text)
    urls: list[str] = []
    for candidate in candidates:
        cleaned = _clean_url(candidate)
        if cleaned:
            urls.append(cleaned)
    return _dedupe_strings(urls)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _clean_url(value) if value.startswith(("http://", "https://")) else value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _clean_url(value: str) -> str:
    cleaned = value.strip().split("\\n", 1)[0].split("\n", 1)[0]
    return cleaned.rstrip("`.,;:]}）】-")


def _safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unknown"


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stringify_paths(paths: list[Path]) -> list[str]:
    seen: dict[str, None] = {}
    for path in paths:
        if path.exists():
            seen[str(path)] = None
    return sorted(seen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a supervisor orchestration run from its artifacts.",
    )
    parser.add_argument("run_dir", type=Path, help="Path to orchestration_runs/<run_id>.")
    args = parser.parse_args(argv)
    result = write_evaluation_for_run(args.run_dir)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
