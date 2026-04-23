"""Automated scoring helpers for complex QA runs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import time
from typing import Any

from code2workspace_cli.config import create_model
from dotenv import load_dotenv


def build_rule_score(result: dict[str, Any]) -> dict[str, Any]:
    """Compute a lightweight structural score before model judging."""
    answer_text = Path(str(result["answer_path"])).read_text(encoding="utf-8")
    trace_payload = json.loads(Path(str(result["trace_path"])).read_text(encoding="utf-8"))

    checks = {
        "runtime_ok": result.get("status") != "runner_error",
        "answer_nonempty": bool(answer_text.strip()),
        "trace_exists": Path(str(result["trace_path"])).exists(),
        "has_tool_trace": bool(result.get("tool_invocations")),
        "has_source_signal": bool(result.get("source_urls")),
    }
    return {
        "total": sum(4 for passed in checks.values() if passed),
        "checks": checks,
        "answer_char_count": int(trace_payload.get("answer_char_count", 0)),
        "tool_invocation_count": int(trace_payload.get("tool_invocation_count", 0)),
    }


def build_judge_prompt(*, result: dict[str, Any], rule_score: dict[str, Any]) -> str:
    """Build the model-judge prompt for one complex QA result."""
    answer_text = Path(str(result["answer_path"])).read_text(encoding="utf-8")
    trace_payload = json.loads(Path(str(result["trace_path"])).read_text(encoding="utf-8"))
    judge_input = {
        "question": result.get("prompt"),
        "task_family": result.get("task_family"),
        "question_type": result.get("question_type"),
        "preferred_skills": result.get("preferred_skills", []),
        "judge_focus": result.get("judge_focus", []),
        "answer": answer_text,
        "trace": trace_payload,
        "rule_score": rule_score,
    }
    return (
        "You are grading a complex QA run.\n"
        "Score only the final answer and execution trace you are given.\n"
        "Return strict JSON with keys: overall_score, judge_score, rule_score, "
        "dimension_scores, verdict, major_issues, trace_findings, improvement_hints.\n"
        "Scoring rubric:\n"
        "- accuracy: 0-30\n"
        "- completeness: 0-20\n"
        "- reasonableness: 0-15\n"
        "- trace_rationality: 0-15\n"
        "Set judge_score to the sum of the four dimensions. Set overall_score to 0; "
        "the caller will replace it.\n\n"
        f"{json.dumps(judge_input, ensure_ascii=False, indent=2)}"
    )


def invoke_judge_model(prompt: str, model_spec: str = "openai:gpt-5.4") -> str:
    """Invoke the configured chat model for offline judging."""
    load_dotenv(_repo_root() / ".env")
    model = create_model(
        model_spec,
        extra_kwargs={
            "reasoning_effort": "low",
            "timeout": 90.0,
        },
    ).model
    response = model.invoke(prompt)
    return _message_text(response.content)


def parse_judge_output(text: str) -> dict[str, Any]:
    """Parse one model-judge response into JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    return {
        "overall_score": _coerce_int_value(payload["overall_score"]),
        "judge_score": _coerce_int_value(payload["judge_score"]),
        "rule_score": _coerce_int_value(payload["rule_score"]),
        "dimension_scores": {
            "accuracy": _coerce_int_value(payload["dimension_scores"]["accuracy"]),
            "completeness": _coerce_int_value(payload["dimension_scores"]["completeness"]),
            "reasonableness": _coerce_int_value(payload["dimension_scores"]["reasonableness"]),
            "trace_rationality": _coerce_int_value(payload["dimension_scores"]["trace_rationality"]),
        },
        "verdict": str(payload["verdict"]),
        "major_issues": [str(item) for item in payload.get("major_issues", [])],
        "trace_findings": [str(item) for item in payload.get("trace_findings", [])],
        "improvement_hints": [str(item) for item in payload.get("improvement_hints", [])],
    }


def judge_case(result: dict[str, Any], model_spec: str = "openai:gpt-5.4") -> dict[str, Any]:
    """Combine structural checks with a model judge for one case."""
    rule_score = build_rule_score(result)
    prompt = build_judge_prompt(result=result, rule_score=rule_score)
    raw = None
    for attempt in range(2):
        try:
            raw = invoke_judge_model(prompt, model_spec=model_spec)
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 1 or not _is_transient_judge_error(str(exc)):
                raise
            time.sleep(2)
    if raw is None:  # pragma: no cover - defensive fallback
        raise RuntimeError("judge produced no response")
    try:
        parsed = parse_judge_output(raw)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        parsed = {
            "overall_score": 0,
            "judge_score": 0,
            "rule_score": 0,
            "dimension_scores": {
                "accuracy": 0,
                "completeness": 0,
                "reasonableness": 0,
                "trace_rationality": 0,
            },
            "verdict": "judge_parse_failed",
            "major_issues": ["judge output was not valid JSON"],
            "trace_findings": [],
            "improvement_hints": [],
        }
    parsed["rule_score"] = rule_score["total"]
    parsed["overall_score"] = int(parsed["judge_score"]) + int(rule_score["total"])
    parsed["rule_checks"] = rule_score["checks"]
    parsed["answer_char_count"] = rule_score["answer_char_count"]
    parsed["tool_invocation_count"] = rule_score["tool_invocation_count"]
    return parsed


def judge_results(
    results: list[dict[str, Any]],
    *,
    run_date: str,
    model_spec: str = "openai:gpt-5.4",
    max_parallel: int = 4,
) -> list[dict[str, Any]]:
    """Judge all case results and persist per-case judge artifacts."""
    def _judge_one(result: dict[str, Any]) -> dict[str, Any]:
        judge_path = _judge_path(result)
        if judge_path.exists():
            judged = json.loads(judge_path.read_text(encoding="utf-8"))
        else:
            judged = judge_case(result, model_spec=model_spec)
            judge_path.write_text(
                json.dumps(judged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return {
            **result,
            **judged,
            "judge_path": str(judge_path),
            "run_date": run_date,
        }

    if max_parallel <= 1 or len(results) <= 1:
        return [_judge_one(result) for result in results]

    indexed_results: list[dict[str, Any] | None] = [None] * len(results)
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        future_to_index = {
            executor.submit(_judge_one, result): index
            for index, result in enumerate(results)
        }
        for future in as_completed(future_to_index):
            indexed_results[future_to_index[future]] = future.result()
    return [item for item in indexed_results if item is not None]


def build_judge_summary_payload(results: list[dict[str, Any]], *, run_date: str) -> dict[str, Any]:
    """Build one machine-readable summary for judged cases."""
    total_score = sum(float(item["overall_score"]) for item in results)
    count = len(results)
    return {
        "date": run_date,
        "case_count": count,
        "average_score": 0.0 if count == 0 else total_score / count,
        "results": results,
    }


def build_judge_summary_zh(results: list[dict[str, Any]], *, run_date: str) -> str:
    """Render a readable Chinese markdown score summary."""
    lines = [
        "# Complex QA Judge Summary",
        "",
        f"- 日期：`{run_date}`",
        f"- 总 case 数：`{len(results)}`",
        "",
    ]
    if results:
        average = sum(float(item["overall_score"]) for item in results) / len(results)
        lines.append(f"- 平均分：`{average:.2f}`")
        lines.append("")
    for result in results:
        dims = result["dimension_scores"]
        lines.extend(
            [
                f"## {result['name']}",
                "",
                f"- 总分：`{result['overall_score']}`",
                f"- 规则分：`{result['rule_score']}`",
                f"- 模型分：`{result['judge_score']}`",
                (
                    "- 维度："
                    f"accuracy={dims['accuracy']}, "
                    f"completeness={dims['completeness']}, "
                    f"reasonableness={dims['reasonableness']}, "
                    f"trace_rationality={dims['trace_rationality']}"
                ),
                f"- 结论：`{result['verdict']}`",
                f"- Judge 文件：`{result['judge_path']}`",
            ]
        )
        if result["major_issues"]:
            lines.append("- 主要问题：" + "；".join(result["major_issues"]))
        if result["trace_findings"]:
            lines.append("- 链路观察：" + "；".join(result["trace_findings"]))
        if result["improvement_hints"]:
            lines.append("- 改进提示：" + "；".join(result["improvement_hints"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_judge_summary_json(path: Path, results: list[dict[str, Any]], *, run_date: str) -> Path:
    """Write the machine-readable judged summary."""
    path.write_text(
        json.dumps(
            build_judge_summary_payload(results, run_date=run_date),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_judge_summary_zh(path: Path, results: list[dict[str, Any]], *, run_date: str) -> Path:
    """Write the Chinese markdown judge summary."""
    path.write_text(build_judge_summary_zh(results, run_date=run_date), encoding="utf-8")
    return path


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
                continue
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
                continue
            parts.append(str(item))
        return "\n".join(parts)
    return "" if content is None else str(content)


def _judge_path(result: dict[str, Any]) -> Path:
    answer_path = Path(str(result["answer_path"]))
    if answer_path.name.endswith(".answer.txt"):
        return answer_path.with_name(answer_path.name.removesuffix(".answer.txt") + ".judge.json")
    return answer_path.with_suffix(".judge.json")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_transient_judge_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "error code: 502",
            "502",
            "bad gateway",
            "overloaded",
            "timeout",
        )
    )


def _coerce_int_value(value: Any) -> int:
    if isinstance(value, dict):
        for key in ("total", "score", "value"):
            if key in value:
                return _coerce_int_value(value[key])
        raise TypeError(f"Cannot coerce dict {value!r} to int")
    return int(value)
