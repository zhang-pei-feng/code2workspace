"""Live evaluation runner for project skills and composite report flows."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.skill_tests.parsers import (
    extract_repo_paths,
    extract_summary_lines,
    parse_subagents,
    parse_tool_invocations,
    parse_tool_names,
)
from experiments.skill_tests.report import (
    extract_final_answer_from_log,
    write_capability_snapshot_zh,
    write_summary_json,
    write_summary_zh,
)


VALID_TARGETS = {"skill", "composite-skill", "oneshot", "harness", "question"}
_BATCH_CASE_RE = re.compile(r"`(?P<case>[^`]+\.toml)`")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cases_root() -> Path:
    return Path(__file__).resolve().parent / "cases"


def results_root() -> Path:
    return repo_root() / "results" / "skill-tests"


def batch_root() -> Path:
    return repo_root() / "experiments" / "skill_tests" / "batches"


def runs_root() -> Path:
    return repo_root() / "experiments" / "skill_tests" / "runs"


def utc_date() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%d")


def utc_stamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class LiveEvalCase:
    target: str
    name: str
    prompt: str
    required_env: tuple[str, ...]
    expected_behaviors: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    known_issues: tuple[str, ...]
    timeout_minutes: int
    allow_timeout_after_expectations: bool
    command: tuple[str, ...] | None
    artifact_root: str | None
    path: Path
    task_family: str | None = None
    question_type: str | None = None
    preferred_skills: tuple[str, ...] = ()
    source_hints: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    judge_focus: tuple[str, ...] = ()
    prior_case_refs: tuple[str, ...] = ()
    weight: float = 1.0


def load_case(path: Path) -> LiveEvalCase:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    required = ("target", "name", "prompt", "required_env", "expected_behaviors", "expected_outputs")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"{path} missing required fields: {missing}")
    target = str(payload["target"])
    if target not in VALID_TARGETS:
        raise ValueError(f"{path} has invalid target {target!r}")
    required_env = tuple(str(item) for item in payload["required_env"])
    expected_behaviors = tuple(str(item) for item in payload["expected_behaviors"])
    expected_outputs = tuple(str(item) for item in payload["expected_outputs"])
    known_issues = tuple(str(item) for item in payload.get("known_issues", []))
    timeout_minutes = int(payload.get("timeout_minutes", 8))
    if timeout_minutes < 1:
        raise ValueError(f"{path} timeout_minutes must be >= 1")
    allow_timeout_after_expectations = bool(payload.get("allow_timeout_after_expectations", False))
    raw_command = payload.get("command")
    command = None if raw_command is None else tuple(str(item) for item in raw_command)
    artifact_root = str(payload["artifact_root"]) if "artifact_root" in payload else None
    return LiveEvalCase(
        target=target,
        name=str(payload["name"]),
        prompt=str(payload["prompt"]),
        required_env=required_env,
        expected_behaviors=expected_behaviors,
        expected_outputs=expected_outputs,
        known_issues=known_issues,
        timeout_minutes=timeout_minutes,
        allow_timeout_after_expectations=allow_timeout_after_expectations,
        command=command,
        artifact_root=artifact_root,
        path=path,
        task_family=str(payload["task_family"]) if "task_family" in payload else None,
        question_type=str(payload["question_type"]) if "question_type" in payload else None,
        preferred_skills=tuple(str(item) for item in payload.get("preferred_skills", [])),
        source_hints=tuple(str(item) for item in payload.get("source_hints", [])),
        source_urls=tuple(str(item) for item in payload.get("source_urls", [])),
        judge_focus=tuple(str(item) for item in payload.get("judge_focus", [])),
        prior_case_refs=tuple(str(item) for item in payload.get("prior_case_refs", [])),
        weight=float(payload.get("weight", 1.0)),
    )


def list_cases(paths: list[Path] | None = None) -> list[LiveEvalCase]:
    if paths:
        return [load_case(path.resolve()) for path in paths]
    return [load_case(path) for path in sorted(cases_root().glob("*.toml"))]


def load_batch_cases(path: Path) -> list[LiveEvalCase]:
    """Load case files referenced from a markdown batch manifest."""
    text = path.read_text(encoding="utf-8")
    case_names: list[str] = []
    for line in text.splitlines():
        match = _BATCH_CASE_RE.search(line)
        if match:
            case_names.append(match.group("case"))
    if not case_names:
        raise ValueError(f"{path} does not reference any .toml case files")
    return [load_case(cases_root() / name) for name in case_names]


def discover_runtime_env() -> dict[str, str]:
    env: dict[str, str] = {}
    data_governance_root = Path("/mnt/data1/zhangpf/superagent/data_governance_agent")
    if data_governance_root.exists():
        env["DATA_GOVERNANCE_AGENT_ROOT"] = str(data_governance_root)
    env["CODE2WORKSPACE_CLI_DISABLE_UPDATE_CHECK"] = "1"
    return env


def run_case(
    case: LiveEvalCase,
    *,
    run_date: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    result_dir = (output_root or results_root()) / run_date
    result_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(case.name)
    log_path = result_dir / f"{slug}.log"
    prompt_path = result_dir / f"{slug}.prompt.txt"
    answer_path = result_dir / f"{slug}.answer.txt"
    trace_path = result_dir / f"{slug}.trace.json"

    runtime_env = os.environ.copy()
    runtime_env.update(discover_runtime_env())
    missing_env = [name for name in case.required_env if not runtime_env.get(name)]

    if case.artifact_root:
        artifact_root = repo_root() / case.artifact_root
        before_artifact_dirs = _list_dirs(artifact_root)
    else:
        artifact_root = None
        before_artifact_dirs = set()

    if missing_env:
        log_path.write_text("", encoding="utf-8")
        prompt_path.write_text(case.prompt, encoding="utf-8")
        answer_path.write_text("", encoding="utf-8")
        parsed = _parsed_log("")
        _write_trace(trace_path, case=case, parsed=parsed, answer_text="")
        result = _finalize_result(
            case=case,
            status="infra_blocked",
            log_path=log_path,
            prompt_path=prompt_path,
            answer_path=answer_path,
            trace_path=trace_path,
            returncode=None,
            log_text="",
            parsed=parsed,
            missing_env=missing_env,
            artifact_root=artifact_root,
            before_artifact_dirs=before_artifact_dirs,
        )
        return result

    prompt_path.write_text(case.prompt, encoding="utf-8")
    command = _build_command(case)
    completed = None
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root(),
            env=runtime_env,
            capture_output=True,
            text=True,
            timeout=case.timeout_minutes * 60,
            check=False,
        )
        log_text = _combine_output(completed.stdout, completed.stderr)
        log_path.write_text(log_text, encoding="utf-8")
        answer_text = extract_final_answer_from_log(log_text)
        answer_path.write_text(answer_text, encoding="utf-8")
        parsed = _parsed_log(log_text)
        _write_trace(trace_path, case=case, parsed=parsed, answer_text=answer_text)
        return _finalize_result(
            case=case,
            status=None,
            log_path=log_path,
            prompt_path=prompt_path,
            answer_path=answer_path,
            trace_path=trace_path,
            returncode=completed.returncode,
            log_text=log_text,
            parsed=parsed,
            missing_env=[],
            artifact_root=artifact_root,
            before_artifact_dirs=before_artifact_dirs,
        )
    except subprocess.TimeoutExpired as exc:
        log_text = _combine_output(exc.stdout or "", exc.stderr or "")
        log_path.write_text(log_text, encoding="utf-8")
        answer_text = extract_final_answer_from_log(log_text)
        answer_path.write_text(answer_text, encoding="utf-8")
        parsed = _parsed_log(log_text)
        _write_trace(trace_path, case=case, parsed=parsed, answer_text=answer_text)
        timeout_status = "runner_error"
        timeout_error = f"Timed out after {case.timeout_minutes} minute(s)"
        if case.allow_timeout_after_expectations:
            timeout_status = None
            timeout_error = None
        return _finalize_result(
            case=case,
            status=timeout_status,
            log_path=log_path,
            prompt_path=prompt_path,
            answer_path=answer_path,
            trace_path=trace_path,
            returncode=None,
            log_text=log_text,
            parsed=parsed,
            missing_env=[],
            artifact_root=artifact_root,
            before_artifact_dirs=before_artifact_dirs,
            runner_error=timeout_error,
        )


def _build_command(case: LiveEvalCase) -> list[str]:
    if case.command is not None:
        return list(case.command)
    if case.target in {"skill", "composite-skill", "question"}:
        return [
            "uv",
            "run",
            "--project",
            str(repo_root() / "libs" / "cli"),
            "code2workspace",
            "--session-workdir-mode",
            "inherit",
            "--shell-allow-list",
            "all",
            "-n",
            case.prompt,
            "-q",
            "--no-mcp",
        ]
    raise ValueError(f"target {case.target!r} requires an explicit command")


def _parsed_log(log_text: str) -> dict[str, Any]:
    tool_invocations = parse_tool_invocations(log_text)
    return {
        "tool_invocations": tool_invocations,
        "tool_names": parse_tool_names(log_text),
        "subagents": parse_subagents(log_text),
        "summary_lines": extract_summary_lines(log_text),
        "repo_paths": [str(path) for path in extract_repo_paths(log_text)],
    }


def _finalize_result(
    *,
    case: LiveEvalCase,
    status: str | None,
    log_path: Path,
    prompt_path: Path,
    answer_path: Path,
    trace_path: Path,
    returncode: int | None,
    log_text: str,
    parsed: dict[str, Any],
    missing_env: list[str],
    artifact_root: Path | None,
    before_artifact_dirs: set[Path],
    runner_error: str | None = None,
) -> dict[str, Any]:
    artifact_context = _build_artifact_context(log_text, artifact_root, before_artifact_dirs)
    expectation_pool = {
        **parsed,
        **artifact_context,
        "log_text": log_text,
        "returncode": returncode,
    }
    failed_expectations = [
        item
        for item in (*case.expected_behaviors, *case.expected_outputs)
        if not _matches(item, expectation_pool)
    ]
    known_issue_hits = [item for item in case.known_issues if _matches(item, expectation_pool)]

    if status is None:
        if returncode not in (None, 0):
            final_status = "runner_error"
            runner_error = runner_error or f"Non-zero exit code: {returncode}"
        elif known_issue_hits:
            final_status = "known_issue"
        elif failed_expectations:
            final_status = "behavior_regression"
        else:
            final_status = "passed"
    else:
        final_status = status

    if runner_error is not None:
        conclusion = f"运行器错误：{runner_error}"
    elif missing_env:
        conclusion = f"缺少必需环境变量：{', '.join(missing_env)}"
    elif final_status == "passed":
        conclusion = "行为与输出均满足预期。"
    elif final_status == "known_issue":
        conclusion = "命中了已知问题轨道；结果已记录但不视为通过。"
    elif final_status == "infra_blocked":
        conclusion = "基础设施前置条件缺失，未执行 live eval。"
    else:
        conclusion = (
            "存在未满足的行为或输出预期："
            + ", ".join(failed_expectations[:4])
        )

    return {
        "name": case.name,
        "target": case.target,
        "case_file": str(case.path),
        "prompt": case.prompt,
        "prompt_path": str(prompt_path),
        "log_path": str(log_path),
        "answer_path": str(answer_path),
        "trace_path": str(trace_path),
        "status": final_status,
        "returncode": returncode,
        "missing_env": missing_env,
        "failed_expectations": failed_expectations,
        "known_issue_hits": known_issue_hits,
        "tool_invocations": parsed["tool_invocations"],
        "tool_names": parsed["tool_names"],
        "subagents": parsed["subagents"],
        "summary_lines": parsed["summary_lines"],
        "artifact_context": artifact_context,
        "conclusion_zh": conclusion,
        "task_family": case.task_family,
        "question_type": case.question_type,
        "preferred_skills": list(case.preferred_skills),
        "source_hints": list(case.source_hints),
        "source_urls": list(case.source_urls),
        "judge_focus": list(case.judge_focus),
        "prior_case_refs": list(case.prior_case_refs),
        "weight": case.weight,
    }


def _write_trace(
    path: Path,
    *,
    case: LiveEvalCase,
    parsed: dict[str, Any],
    answer_text: str,
) -> None:
    payload = {
        "case_name": case.name,
        "tool_invocations": parsed["tool_invocations"],
        "tool_names": parsed["tool_names"],
        "subagents": parsed["subagents"],
        "summary_lines": parsed["summary_lines"],
        "repo_paths": parsed["repo_paths"],
        "tool_invocation_count": len(parsed["tool_invocations"]),
        "answer_char_count": len(answer_text.strip()),
        "trace_warnings": [],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_artifact_context(
    log_text: str,
    artifact_root: Path | None,
    before_artifact_dirs: set[Path],
) -> dict[str, Any]:
    created_dirs: list[Path] = []
    if artifact_root is not None:
        after_dirs = _list_dirs(artifact_root)
        created_dirs = sorted(after_dirs - before_artifact_dirs)

    run_dir = _extract_run_dir(log_text, created_dirs)
    context: dict[str, Any] = {
        "artifact_created_dirs": [str(path) for path in created_dirs],
        "artifact_new_run_dir": str(run_dir) if run_dir else None,
        "report_final_exists": False,
        "report_char_count": 0,
        "report_meets_min_chars": False,
        "report_lane_count": 0,
        "report_sources_count": 0,
        "report_has_risk_level": False,
        "report_complete": False,
        "report_source_class_count": 0,
        "report_missing_lane_count": 0,
    }
    if run_dir is None:
        return context

    report_path = run_dir / "final_report.md"
    lanes_dir = run_dir / "lanes"
    diagnostics_path = run_dir / "report_diagnostics.json"
    context["report_final_exists"] = report_path.exists()
    if lanes_dir.exists():
        non_empty_lane_files = [
            path
            for path in sorted(lanes_dir.glob("*.md"))
            if path.read_text(encoding="utf-8").strip()
        ]
        context["report_lane_count"] = len(non_empty_lane_files)
    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        in_sources = False
        sources_count = 0
        for line in report_text.splitlines():
            if line.strip() == "## Sources":
                in_sources = True
                continue
            if in_sources and line.startswith("## "):
                break
            if in_sources and line.strip().startswith("- "):
                sources_count += 1
        context["report_sources_count"] = sources_count
        context["report_has_risk_level"] = "- Risk level:" in report_text
    if diagnostics_path.exists():
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        context["report_complete"] = bool(diagnostics.get("complete"))
        context["report_char_count"] = int(diagnostics.get("report_char_count", 0))
        context["report_meets_min_chars"] = bool(
            diagnostics.get("meets_min_report_chars", False)
        )
        lane_diagnostics = diagnostics.get("lane_diagnostics", {})
        if isinstance(lane_diagnostics, dict):
            context["report_lane_count"] = sum(
                1
                for item in lane_diagnostics.values()
                if isinstance(item, dict) and item.get("has_evidence")
            )
        context["report_source_class_count"] = int(
            diagnostics.get("source_class_count", 0)
        )
        context["report_missing_lane_count"] = len(
            diagnostics.get("missing_required_lanes", [])
        )
    return context


def _extract_run_dir(log_text: str, created_dirs: list[Path]) -> Path | None:
    for path in extract_repo_paths(log_text):
        if "results/skills/epidemic-warning-report" not in str(path):
            continue
        if path.name == "final_report.md":
            return path.parent
        if path.is_dir():
            return path
    return created_dirs[-1] if created_dirs else None


def _matches(expectation: str, context: dict[str, Any]) -> bool:
    if expectation.startswith("tool:"):
        needle = expectation.removeprefix("tool:")
        return needle in context["tool_names"]
    if expectation.startswith("not-tool:"):
        needle = expectation.removeprefix("not-tool:")
        return needle not in context["tool_names"]
    if expectation.startswith("subagent:"):
        needle = expectation.removeprefix("subagent:")
        return needle in context["subagents"]
    if expectation.startswith("not-subagent:"):
        needle = expectation.removeprefix("not-subagent:")
        return needle not in context["subagents"]
    if expectation.startswith("tool-count:"):
        target, count = expectation.removeprefix("tool-count:").split(">=", 1)
        return context["tool_names"].count(target) >= int(count)
    if expectation.startswith("subagent-count>="):
        count = int(expectation.removeprefix("subagent-count>="))
        return len(context["subagents"]) >= count
    if expectation.startswith("log:"):
        needle = expectation.removeprefix("log:")
        return needle in context["log_text"]
    if expectation.startswith("not-log:"):
        needle = expectation.removeprefix("not-log:")
        return needle not in context["log_text"]
    if expectation.startswith("summary:"):
        needle = expectation.removeprefix("summary:")
        return any(needle in line for line in context["summary_lines"])
    if expectation.startswith("path-exists:"):
        raw = expectation.removeprefix("path-exists:")
        path = Path(raw)
        if not path.is_absolute():
            path = repo_root() / raw
        return path.exists()
    if expectation.startswith("glob-exists:"):
        pattern = expectation.removeprefix("glob-exists:")
        return any(repo_root().glob(pattern))
    if expectation == "artifact:new-run-dir":
        return context["artifact_new_run_dir"] is not None
    if expectation == "report-final-exists":
        return bool(context["report_final_exists"])
    if expectation.startswith("report-lane-count>="):
        count = int(expectation.removeprefix("report-lane-count>="))
        return int(context["report_lane_count"]) >= count
    if expectation.startswith("report-sources-count>="):
        count = int(expectation.removeprefix("report-sources-count>="))
        return int(context["report_sources_count"]) >= count
    if expectation == "report-risk-level":
        return bool(context["report_has_risk_level"])
    if expectation == "report-complete":
        return bool(context["report_complete"])
    if expectation.startswith("report-char-count>="):
        count = int(expectation.removeprefix("report-char-count>="))
        return int(context["report_char_count"]) >= count
    if expectation == "report-meets-min-chars":
        return bool(context["report_meets_min_chars"])
    if expectation.startswith("report-source-class-count>="):
        count = int(expectation.removeprefix("report-source-class-count>="))
        return int(context["report_source_class_count"]) >= count
    if expectation.startswith("report-missing-lane-count<="):
        count = int(expectation.removeprefix("report-missing-lane-count<="))
        return int(context["report_missing_lane_count"]) <= count
    raise ValueError(f"Unsupported expectation matcher: {expectation}")


def _combine_output(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    left = _coerce_text(stdout)
    right = _coerce_text(stderr)
    if left and right:
        return left + ("\n" if not left.endswith("\n") else "") + right
    return left or right


def _coerce_text(payload: str | bytes | None) -> str:
    if payload is None:
        return ""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


def _list_dirs(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_dir()}


def _slugify(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=utc_date())
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--batch-file", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--list-cases", action="store_true")
    return parser


def run_cases(
    cases: list[LiveEvalCase],
    *,
    run_date: str,
    output_root: Path,
    pinned_snapshot_root: Path | None = None,
) -> dict[str, Any]:
    results = [run_case(case, run_date=run_date, output_root=output_root) for case in cases]
    result_dir = output_root / run_date
    summary_payload = {
        "date": run_date,
        "results": results,
    }
    summary_path = write_summary_json(result_dir / "summary.json", summary_payload)
    summary_zh_path = write_summary_zh(result_dir / "SUMMARY_ZH.md", results, run_date=run_date)
    snapshot_path = write_capability_snapshot_zh(
        result_dir / "CAPABILITY_SNAPSHOT_ZH.md",
        results,
        run_date=run_date,
    )
    pinned_snapshot_path = None
    if pinned_snapshot_root is not None:
        pinned_snapshot_path = write_capability_snapshot_zh(
            pinned_snapshot_root / run_date / "CAPABILITY_SNAPSHOT_ZH.md",
            results,
            run_date=run_date,
        )
    return {
        "date": run_date,
        "result_dir": result_dir,
        "summary_path": summary_path,
        "summary_zh_path": summary_zh_path,
        "capability_snapshot_path": snapshot_path,
        "pinned_snapshot_path": pinned_snapshot_path,
        "results": results,
    }


def main() -> int:
    args = build_parser().parse_args()
    case_paths = [cases_root() / item for item in args.case] if args.case else []
    cases = list_cases(case_paths or None)
    if args.batch_file is not None:
        batch_cases = load_batch_cases(args.batch_file)
        if case_paths:
            seen = {case.path.resolve() for case in cases}
            for case in batch_cases:
                if case.path.resolve() not in seen:
                    cases.append(case)
        else:
            cases = batch_cases
    if args.list_cases:
        for case in cases:
            print(case.path.name)
        return 0

    output_root = args.output_root or results_root()
    pinned_root = (
        repo_root() / "experiments" / "skill_tests" / "snapshots"
        if args.output_root is not None
        else repo_root() / "experiments" / "skill_tests" / "snapshots"
    )
    bundle = run_cases(
        cases,
        run_date=args.date,
        output_root=output_root,
        pinned_snapshot_root=pinned_root,
    )
    print(
        json.dumps(
            {
                "date": args.date,
                "summary_path": str(bundle["summary_path"]),
                "capability_snapshot_path": str(bundle["capability_snapshot_path"]),
                "pinned_snapshot_path": (
                    str(bundle["pinned_snapshot_path"])
                    if bundle["pinned_snapshot_path"] is not None
                    else None
                ),
                "result_dir": str(bundle["result_dir"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
