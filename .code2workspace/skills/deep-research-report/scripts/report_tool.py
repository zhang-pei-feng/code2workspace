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

from common import create_skill_run_dir, ensure_dir, read_json, write_json, write_text
from report_composer import collect_lane_info, render_lane_evidence, write_composed_report


def cmd_init(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("deep-research-report", args.topic)
    ensure_dir(run_dir / "lanes")
    write_text(run_dir / "research_request.md", f"# Research Request\n\n{args.topic}\n")
    write_json(
        run_dir / "manifest.json",
        {
            "run_dir": str(run_dir),
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
    manifest_path = run_dir / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    topic = manifest.get("topic", "Research Topic")
    lane_info_by_file = collect_lane_info(lanes_dir)

    sections = [
        {
            "title": "Executive Summary",
            "body": args.summary
            or "This report synthesizes the available research lanes and keeps only source-backed evidence in the final answer.",
        }
    ]
    for lane_file, lane_info in lane_info_by_file.items():
        sections.append(
            {
                "title": str(lane_info["title"]),
                "body": render_lane_evidence(lane_file, lane_info),
                "lane_file": lane_file,
            }
        )
    if not lane_info_by_file:
        sections.append(
            {
                "title": "Pending Evidence",
                "body": "_This run does not contain any lane notes yet. Add source-backed lane notes before treating the report as complete._",
            }
        )
    sections.append(
        {
            "title": "Cross-Lane Synthesis",
            "body": (
                "Compare the lane findings here, highlight points of agreement and disagreement, "
                "and separate strong source-backed conclusions from open evidence gaps."
            ),
        }
    )

    payload = write_composed_report(
        run_dir=run_dir,
        title=str(topic),
        sections=sections,
        lane_info_by_file=lane_info_by_file,
        header_lines=[f"- Output directory: `{run_dir}`"],
        min_report_chars=0,
    )
    print(json.dumps({"run_dir": str(run_dir), **payload}, ensure_ascii=False, indent=2))
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
