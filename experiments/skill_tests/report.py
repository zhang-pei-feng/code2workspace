"""Summary generation for live skill evaluations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def write_summary_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write machine-readable summary output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def build_summary_zh(results: list[dict[str, Any]], *, run_date: str) -> str:
    """Render a concise Chinese markdown summary for one live-eval run."""
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1

    lines = [
        "# 技能评测汇总",
        "",
        f"- 日期：`{run_date}`",
        f"- 总 case 数：`{len(results)}`",
        f"- 通过：`{counts.get('passed', 0)}`",
        f"- 已知问题：`{counts.get('known_issue', 0)}`",
        f"- 基础设施阻塞：`{counts.get('infra_blocked', 0)}`",
        f"- 行为回归：`{counts.get('behavior_regression', 0)}`",
        f"- Runner 错误：`{counts.get('runner_error', 0)}`",
        "",
    ]

    for result in results:
        lines.extend(
            [
                f"## {result['name']}",
                "",
                f"- 目标：`{result['target']}`",
                f"- 状态：`{result['status']}`",
                f"- 结论：{result['conclusion_zh']}",
                f"- 日志：`{result['log_path']}`",
            ]
        )
        if result.get("failed_expectations"):
            lines.append(
                "- 未满足项：" + ", ".join(f"`{item}`" for item in result["failed_expectations"])
            )
        if result.get("known_issue_hits"):
            lines.append(
                "- 命中的已知问题：" + ", ".join(f"`{item}`" for item in result["known_issue_hits"])
            )
        lines.append("")
    return "\n".join(lines)


def write_summary_zh(path: Path, results: list[dict[str, Any]], *, run_date: str) -> Path:
    """Write the Chinese markdown summary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_summary_zh(results, run_date=run_date) + "\n", encoding="utf-8")
    return path


_TOOL_TRACE_RE = re.compile(r"Calling tool:\s*")


def extract_final_answer_from_log(log_text: str) -> str:
    """Extract the final natural-language answer from a live-eval log.

    Live-eval logs usually contain the final assistant answer mixed with tool
    trace lines (e.g. 'Calling tool: ...'). For capability snapshots we want
    the human-readable answer with tool traces removed.
    """
    kept: list[str] = []
    for raw_line in log_text.splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            kept.append("")
            continue
        if _TOOL_TRACE_RE.search(line):
            continue
        if line.startswith("Warning: Web search is disabled"):
            continue
        kept.append(line)

    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    return ("\n".join(kept).strip() + "\n") if kept else ""


def build_capability_snapshot_zh(results: list[dict[str, Any]], *, run_date: str) -> str:
    """Render a full 'input + output' capability snapshot markdown."""
    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1

    lines: list[str] = [
        "# 能力快照（输入输出）",
        "",
        f"- 日期：`{run_date}`",
        f"- 总 case 数：`{len(results)}`",
        f"- 通过：`{counts.get('passed', 0)}`",
        f"- 已知问题：`{counts.get('known_issue', 0)}`",
        f"- 基础设施阻塞：`{counts.get('infra_blocked', 0)}`",
        f"- 行为回归：`{counts.get('behavior_regression', 0)}`",
        f"- Runner 错误：`{counts.get('runner_error', 0)}`",
        "",
    ]

    for result in results:
        prompt = str(result.get("prompt") or "")
        log_path = Path(str(result.get("log_path") or ""))
        if str(log_path) and log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            final_answer = extract_final_answer_from_log(log_text)
        else:
            final_answer = ""

        lines.extend(
            [
                f"## {result['name']}",
                "",
                f"- 目标：`{result['target']}`",
                f"- 状态：`{result['status']}`",
                f"- 结论：{result['conclusion_zh']}",
                f"- 日志：`{result['log_path']}`",
                "",
                "### 输入",
                "",
                "```text",
                prompt.strip(),
                "```",
                "",
                "### 输出（最终回答，过滤 tool trace）",
                "",
                "```text",
                final_answer.rstrip("\n"),
                "```",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_capability_snapshot_zh(path: Path, results: list[dict[str, Any]], *, run_date: str) -> Path:
    """Write the full capability snapshot markdown."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_capability_snapshot_zh(results, run_date=run_date), encoding="utf-8")
    return path
