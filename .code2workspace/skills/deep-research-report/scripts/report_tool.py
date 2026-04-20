#!/usr/bin/env python3
"""Scaffold and compose deep research report runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED_HELPER_DIR = Path(__file__).resolve().parents[2] / "_shared-superagent-helpers" / "scripts"
if str(SHARED_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HELPER_DIR))

from common import create_skill_run_dir, ensure_dir, write_json, write_text


def cmd_init(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("deep-research-report", args.topic)
    ensure_dir(run_dir / "lanes")
    write_text(run_dir / "research_request.md", f"# Research Request\n\n{args.topic}\n")
    write_json(
        run_dir / "manifest.json",
        {
            "topic": args.topic,
            "language": args.language,
            "lanes_dir": str(run_dir / "lanes"),
        },
    )
    print(json.dumps({"run_dir": str(run_dir), "topic": args.topic}, ensure_ascii=False, indent=2))
    return 0


def cmd_compose(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    lanes_dir = run_dir / "lanes"
    lane_files = sorted(lanes_dir.glob("*.md"))
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    topic = manifest.get("topic", "Research Topic")

    sections = []
    sources = []
    for lane_file in lane_files:
        content = lane_file.read_text(encoding="utf-8").strip()
        if not content:
            continue
        sections.append(f"## {lane_file.stem}\n\n{content}")
        for line in content.splitlines():
            if line.lower().startswith("source:"):
                sources.append(line.split(":", 1)[1].strip())

    report = [
        f"# {topic}",
        "",
        "## Executive Summary",
        "",
        args.summary or "This report composes the available research lanes generated for the topic.",
        "",
    ]
    report.extend(sections or ["## Pending\n\nNo lane notes were found.\n"])
    report.append("## Sources\n")
    if sources:
        report.extend(f"- {item}" for item in dict.fromkeys(sources))
    else:
        report.append("- No explicit sources were recorded in lane notes.")
    report_text = "\n".join(report) + "\n"
    write_text(run_dir / "final_report.md", report_text)
    print(json.dumps({"run_dir": str(run_dir), "report_path": str(run_dir / 'final_report.md')}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deep research report scaffolding tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a deep research run directory.")
    init.add_argument("--topic", required=True)
    init.add_argument("--language", default="auto")
    init.add_argument("--output-dir")
    init.set_defaults(func=cmd_init)

    compose = subparsers.add_parser("compose", help="Compose the final report from lane notes.")
    compose.add_argument("--run-dir", required=True)
    compose.add_argument("--summary", help="Optional executive summary override.")
    compose.set_defaults(func=cmd_compose)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
