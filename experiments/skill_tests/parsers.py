"""Parsers for non-interactive live-eval logs."""

from __future__ import annotations

import re
from pathlib import Path


TOOL_CALL_RE = re.compile(r"Calling tool:\s*(?P<display>.+)")
SUBAGENT_RE = re.compile(r"^task\s+\[(?P<subagent>[^\]]+)\]$")
REPO_PATH_RE = re.compile(r"/mnt/data1/zhangpf/code2workspace[^\s`\"']+")
SUBAGENT_BULLET_RE = re.compile(r"^-\s+`(?P<subagent>[a-z0-9-]+)`$")
SUBAGENT_INLINE_RE = re.compile(r"Subagent:\s*(?P<subagent>[a-z0-9-]+)")


def parse_tool_invocations(log_text: str) -> list[dict[str, str | None]]:
    """Extract tool call displays, tool names, and optional subagent names."""
    parsed: list[dict[str, str | None]] = []
    for raw_line in log_text.splitlines():
        line = _strip_ansi(raw_line)
        match = TOOL_CALL_RE.search(line)
        if not match:
            continue
        display = match.group("display").strip()
        normalized = re.sub(r"^\(\*\)\s*", "", display)
        tool_name = normalized.split("(", 1)[0].split()[0].strip() if normalized else ""
        subagent = None
        subagent_match = SUBAGENT_RE.match(normalized)
        if subagent_match:
            subagent = subagent_match.group("subagent")
            tool_name = "task"
        parsed.append(
            {
                "display": normalized,
                "tool": tool_name or None,
                "subagent": subagent,
            }
        )
    return parsed


def parse_tool_names(log_text: str) -> list[str]:
    """Return tool names in call order."""
    return [item["tool"] for item in parse_tool_invocations(log_text) if item["tool"]]


def parse_subagents(log_text: str) -> list[str]:
    """Return subagent types referenced by task tool invocations."""
    subagents = [item["subagent"] for item in parse_tool_invocations(log_text) if item["subagent"]]
    for raw_line in log_text.splitlines():
        line = _strip_ansi(raw_line).strip()
        bullet_match = SUBAGENT_BULLET_RE.match(line)
        inline_match = SUBAGENT_INLINE_RE.search(line)
        if bullet_match:
            subagents.append(bullet_match.group("subagent"))
        elif inline_match:
            subagents.append(inline_match.group("subagent"))
    ordered: list[str] = []
    seen: set[str] = set()
    for item in subagents:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def extract_summary_lines(log_text: str, *, limit: int = 12) -> list[str]:
    """Return the trailing non-tool, non-empty lines from a log."""
    summary_lines: list[str] = []
    for raw_line in log_text.splitlines():
        line = _strip_ansi(raw_line).strip()
        if not line:
            continue
        if "Calling tool:" in line:
            continue
        if line.startswith("Warning: Web search is disabled"):
            continue
        summary_lines.append(line)
    if len(summary_lines) <= limit:
        return summary_lines
    return summary_lines[-limit:]


def extract_repo_paths(log_text: str) -> list[Path]:
    """Return unique repo-local absolute paths mentioned in the log."""
    discovered = [Path(item) for item in REPO_PATH_RE.findall(_strip_ansi(log_text))]
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in discovered:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
