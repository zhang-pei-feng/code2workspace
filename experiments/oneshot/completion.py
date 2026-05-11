"""Completion rubric loading and evidence-based run judgment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.oneshot.miniwdl import miniwdl_run_marker


def repo_root() -> Path:
    """Return the project repository root."""
    return Path(__file__).resolve().parents[2]


def completion_rubric_path() -> Path:
    """Return the shared harness completion rubric path."""
    return repo_root() / "experiments" / "harness" / "surfaces" / "completion_rubric.txt"


def load_completion_rubric() -> str:
    """Load the shared completion rubric text."""
    return completion_rubric_path().read_text(encoding="utf-8")


def capture_completion_snapshot(target_repo: Path, spec: Any) -> dict[str, dict[str, Any]]:
    """Capture the tracked workspace state before or after one run."""
    tracked = {
        "dockerfile": target_repo / spec.dockerfile_name,
        "wdl": target_repo / spec.wdl_name,
        "inputs_json": target_repo / "inputs.json",
        "docker_test_dir": target_repo / "results" / "docker_test",
        "wdl_result_dir": target_repo / "results" / "wdl_result",
        "wdl_file_dir": target_repo / "results" / "wdl_file",
        "docker_build_log": target_repo / "results" / "docker_test" / "docker_build.log",
        "docker_build_retry_log": target_repo / "results" / "docker_test" / "docker_build_retry.log",
        "docker_image_inspect_log": target_repo / "results" / "docker_test" / "docker_image_inspect.log",
        "docker_run_log": target_repo / "results" / "docker_test" / "docker_run.log",
        "docker_run_test_log": target_repo / "results" / "docker_test" / "docker_run_test.log",
        "test_run_log": target_repo / "results" / "docker_test" / "test_run.log",
        "miniwdl_run_log": target_repo / "results" / "wdl_result" / "miniwdl_run.log",
        "miniwdl_run_retry_log": target_repo / "results" / "wdl_result" / "miniwdl_run_retry.log",
        "outputs_json": target_repo / "results" / "wdl_result" / "outputs.json",
        "outputs_retry_json": target_repo / "results" / "wdl_result" / "outputs_retry.json",
        "copied_wdl": target_repo / "results" / "wdl_file" / spec.wdl_name,
        "copied_inputs": target_repo / "results" / "wdl_file" / "inputs.json",
    }
    return {
        name: _snapshot_path(path)
        for name, path in tracked.items()
    }


def judge_completion(
    *,
    spec: Any,
    target_repo: Path,
    before: dict[str, dict[str, Any]],
    output: str,
    returncode: int,
    interrupted: bool,
    timed_out: bool,
    rubric_text: str | None = None,
) -> dict[str, Any]:
    """Judge one run against the shared completion rubric."""
    rubric = rubric_text or load_completion_rubric()
    after = capture_completion_snapshot(target_repo, spec)

    docker_logs = _join_changed_files(
        after=after,
        before=before,
        target_repo=target_repo,
        keys=(
            "docker_build_log",
            "docker_build_retry_log",
            "docker_image_inspect_log",
            "docker_run_log",
            "docker_run_test_log",
            "test_run_log",
        ),
    )
    miniwdl_log_texts = _read_matching_files(
        path=target_repo / "results" / "wdl_result",
        pattern="miniwdl_run*.log",
        before_state=before["wdl_result_dir"],
    )
    miniwdl_logs = "\n".join(miniwdl_log_texts)

    wdl_file_text = _read_text_if_exists(target_repo / spec.wdl_name)
    copied_wdl_text = _read_text_if_exists(target_repo / "results" / "wdl_file" / spec.wdl_name)
    outputs_payload = _load_latest_matching_json(
        path=target_repo / "results" / "wdl_result",
        pattern="outputs*.json",
        before_state=before["wdl_result_dir"],
    )
    fresh_docker_outputs = _fresh_non_log_files(
        path=target_repo / "results" / "docker_test",
        before_state=before["docker_test_dir"],
    )
    fresh_docker_execution_logs = _fresh_docker_execution_logs(
        path=target_repo / "results" / "docker_test",
        before_state=before["docker_test_dir"],
    )
    fresh_wdl_outputs = _fresh_non_log_files(
        path=target_repo / "results" / "wdl_result",
        before_state=before["wdl_result_dir"],
    )
    fresh_wdl_inputs = _fresh_non_log_files(
        path=target_repo / "results" / "wdl_file",
        before_state=before["wdl_file_dir"],
    )

    evidence = {
        "returncode_zero": _make_evidence(
            passed=returncode == 0,
            detail=f"returncode={returncode}",
        ),
        "not_interrupted": _make_evidence(
            passed=not interrupted,
            detail=f"interrupted={interrupted}",
        ),
        "not_timed_out": _make_evidence(
            passed=not timed_out,
            detail=f"timed_out={timed_out}",
        ),
        "final_answer_declares_completed": _make_evidence(
            passed="COMPLETED" in output.upper(),
            detail="agent output contains `COMPLETED`" if "COMPLETED" in output.upper() else "agent output does not contain `COMPLETED`",
        ),
        "dockerfile_written": _make_evidence(
            passed=after["dockerfile"]["exists"] and _path_changed(before["dockerfile"], after["dockerfile"]),
            detail=_path_change_detail(before["dockerfile"], after["dockerfile"], target_repo / spec.dockerfile_name),
        ),
        "docker_image_matches_repo": _make_evidence(
            passed=(
                after["docker_image_inspect_log"]["exists"]
                and _path_changed(before["docker_image_inspect_log"], after["docker_image_inspect_log"])
                and spec.image_name in docker_logs
            )
            or f"naming to docker.io/library/{spec.image_name}" in docker_logs
            or f"{spec.image_name}:latest" in docker_logs,
            detail=f"expected image `{spec.image_name}` searched in fresh docker logs",
        ),
        "docker_test_executed": _make_evidence(
            passed=bool(fresh_docker_outputs)
            and (
                bool(fresh_docker_execution_logs)
                or _path_changed(before["docker_run_log"], after["docker_run_log"])
                or _path_changed(before["docker_run_test_log"], after["docker_run_test_log"])
                or _path_changed(before["test_run_log"], after["test_run_log"])
            ),
            detail=(
                _fresh_file_detail("results/docker_test", fresh_docker_outputs)
                + "; "
                + _fresh_file_detail("results/docker_test execution logs", fresh_docker_execution_logs)
            ),
        ),
        "wdl_written_for_expected_image": _make_evidence(
            passed=(
                (
                    (
                        after["wdl"]["exists"]
                        and _path_changed(before["wdl"], after["wdl"])
                    )
                    or (
                        after["copied_wdl"]["exists"]
                        and _path_changed(before["copied_wdl"], after["copied_wdl"])
                    )
                )
                and spec.image_name in (wdl_file_text + copied_wdl_text)
            ),
            detail=f"expected image `{spec.image_name}` searched in fresh WDL files",
        ),
        "miniwdl_ran": _make_evidence(
            passed=miniwdl_run_marker() in output
            or bool(miniwdl_log_texts)
            or _path_changed(before["miniwdl_run_log"], after["miniwdl_run_log"])
            or _path_changed(before["miniwdl_run_retry_log"], after["miniwdl_run_retry_log"]),
            detail="fresh miniwdl log or explicit command invocation detected",
        ),
        "wdl_succeeded": _make_evidence(
            passed=(
                "done" in miniwdl_logs.lower()
                or bool(outputs_payload.get("outputs"))
            ),
            detail=f"outputs keys={list(outputs_payload.get('outputs', {}).keys()) if isinstance(outputs_payload.get('outputs'), dict) else 'missing'}",
        ),
        "wdl_outputs_written": _make_evidence(
            passed=bool(fresh_wdl_outputs) and bool(fresh_wdl_inputs),
            detail=(
                _fresh_file_detail("results/wdl_result", fresh_wdl_outputs)
                + "; "
                + _fresh_file_detail("results/wdl_file", fresh_wdl_inputs)
            ),
        ),
    }

    required_checks = (
        "returncode_zero",
        "not_interrupted",
        "not_timed_out",
        "final_answer_declares_completed",
        "dockerfile_written",
        "docker_image_matches_repo",
        "docker_test_executed",
        "wdl_written_for_expected_image",
        "miniwdl_ran",
        "wdl_succeeded",
        "wdl_outputs_written",
    )
    completed = all(bool(evidence[name]["passed"]) for name in required_checks)
    failed_checks = [name for name in required_checks if not evidence[name]["passed"]]
    return {
        "completed": completed,
        "rubric_path": str(completion_rubric_path()),
        "rubric_text": rubric,
        "required_checks": list(required_checks),
        "failed_checks": failed_checks,
        "evidence": evidence,
        "workspace_before": before,
        "workspace_after": after,
    }


def _snapshot_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "kind": "missing",
            "path": str(path),
        }
    if path.is_file():
        stat = path.stat()
        return {
            "exists": True,
            "kind": "file",
            "path": str(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    files = sorted(item for item in path.rglob("*") if item.is_file())
    newest_mtime_ns = max((item.stat().st_mtime_ns for item in files), default=path.stat().st_mtime_ns)
    return {
        "exists": True,
        "kind": "dir",
        "path": str(path),
        "file_count": len(files),
        "newest_mtime_ns": newest_mtime_ns,
        "sample_files": [str(item.relative_to(path)) for item in files[:12]],
    }


def _path_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if not after["exists"]:
        return False
    if not before["exists"]:
        return True
    if before["kind"] != after["kind"]:
        return True
    if after["kind"] == "file":
        return (
            before.get("mtime_ns") != after.get("mtime_ns")
            or before.get("size") != after.get("size")
        )
    return (
        before.get("file_count") != after.get("file_count")
        or before.get("newest_mtime_ns") != after.get("newest_mtime_ns")
    )


def _path_change_detail(before: dict[str, Any], after: dict[str, Any], path: Path) -> str:
    if not after["exists"]:
        return f"`{path}` missing after run"
    if not before["exists"]:
        return f"`{path}` created during run"
    if _path_changed(before, after):
        return f"`{path}` changed during run"
    return f"`{path}` unchanged during run"


def _fresh_non_log_files(*, path: Path, before_state: dict[str, Any]) -> list[str]:
    if not path.exists() or not path.is_dir():
        return []
    threshold = before_state.get("newest_mtime_ns", 0) if before_state.get("exists") else 0
    fresh: list[str] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        if item.suffix == ".log":
            continue
        if item.stat().st_mtime_ns > threshold:
            fresh.append(str(item.relative_to(path)))
    return fresh


def _fresh_docker_execution_logs(*, path: Path, before_state: dict[str, Any]) -> list[str]:
    if not path.exists() or not path.is_dir():
        return []
    threshold = before_state.get("newest_mtime_ns", 0) if before_state.get("exists") else 0
    ignored_names = {
        "docker_build.log",
        "docker_build_retry.log",
        "docker_image_inspect.log",
        "docker_image_info.log",
        "docker_version.log",
    }
    fresh: list[str] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file() or item.suffix != ".log":
            continue
        if item.name in ignored_names:
            continue
        if item.stat().st_mtime_ns > threshold:
            fresh.append(str(item.relative_to(path)))
    return fresh


def _read_matching_files(*, path: Path, pattern: str, before_state: dict[str, Any]) -> list[str]:
    if not path.exists() or not path.is_dir():
        return []
    threshold = before_state.get("newest_mtime_ns", 0) if before_state.get("exists") else 0
    texts: list[str] = []
    for item in sorted(path.rglob(pattern)):
        if not item.is_file():
            continue
        if item.stat().st_mtime_ns <= threshold:
            continue
        texts.append(item.read_text(encoding="utf-8", errors="replace"))
    return texts


def _join_changed_files(
    *,
    after: dict[str, dict[str, Any]],
    before: dict[str, dict[str, Any]],
    target_repo: Path,
    keys: tuple[str, ...],
) -> str:
    chunks: list[str] = []
    for key in keys:
        if not _path_changed(before[key], after[key]):
            continue
        path = Path(after[key]["path"])
        if path.exists() and path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_first_json(*, paths: tuple[Path, ...]) -> dict[str, Any]:
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _load_latest_matching_json(*, path: Path, pattern: str, before_state: dict[str, Any]) -> dict[str, Any]:
    if not path.exists() or not path.is_dir():
        return {}
    threshold = before_state.get("newest_mtime_ns", 0) if before_state.get("exists") else 0
    candidates = [
        item
        for item in path.rglob(pattern)
        if item.is_file() and item.stat().st_mtime_ns > threshold
    ]
    for item in sorted(candidates, key=lambda current: current.stat().st_mtime_ns, reverse=True):
        try:
            payload = json.loads(item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _make_evidence(*, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "passed": passed,
        "detail": detail,
    }


def _fresh_file_detail(label: str, fresh_files: list[str]) -> str:
    if not fresh_files:
        return f"`{label}` has no fresh non-log files"
    preview = ", ".join(f"`{item}`" for item in fresh_files[:6])
    if len(fresh_files) > 6:
        preview += ", ..."
    return f"`{label}` fresh files: {preview}"
