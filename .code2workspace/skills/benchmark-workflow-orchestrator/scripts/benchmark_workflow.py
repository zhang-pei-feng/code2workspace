#!/usr/bin/env python3
"""Front-door orchestration helpers for benchmark workflow tasks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED_HELPER_DIR = Path(__file__).resolve().parents[2] / "_shared-superagent-helpers" / "scripts"
if str(SHARED_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HELPER_DIR))

from common import create_skill_run_dir, ensure_dir, read_json, write_json, write_text


def _load_probe_payload(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"ok": False, "reason": "No probe payload was provided."}
    return read_json(path)


def cmd_plan(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("benchmark-workflow-orchestrator", "plan")
    ensure_dir(run_dir)
    payload = {
        "task": args.task,
        "requested_workflows": args.workflow or [],
        "input_paths": [value for value in (args.input_1, args.input_2, args.input_json) if value],
        "bioos_probe": _load_probe_payload(Path(args.probe_json) if args.probe_json else None),
        "next_step": "delegate_to_bioos_operator" if args.workflow else "inspect_or_prepare_inputs",
    }
    write_json(run_dir / "benchmark_plan.json", payload)
    write_text(
        run_dir / "benchmark_plan.md",
        "# Benchmark Plan\n\n"
        f"- task: `{args.task}`\n"
        f"- output_dir: `{run_dir}`\n"
        f"- workflows: {', '.join(args.workflow or ['(unspecified)'])}\n"
        f"- next_step: `{payload['next_step']}`\n",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    source_dir = Path(args.source_dir).resolve()
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("benchmark-workflow-orchestrator", "summary")
    ensure_dir(run_dir)
    files = sorted(str(path.relative_to(source_dir)) for path in source_dir.rglob("*") if path.is_file())
    payload = {
        "source_dir": str(source_dir),
        "file_count": len(files),
        "files": files[: args.max_files],
    }
    write_json(run_dir / "summary.json", payload)
    lines = [
        "# Benchmark Summary",
        "",
        f"- source_dir: `{source_dir}`",
        f"- file_count: `{len(files)}`",
        "",
        "## Files",
        "",
    ]
    lines.extend(f"- `{item}`" for item in files[: args.max_files])
    write_text(run_dir / "summary.md", "\n".join(lines) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark workflow orchestrator helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Materialize a structured benchmark plan stub.")
    plan.add_argument("--task", required=True, help="Natural-language benchmark task.")
    plan.add_argument("--workflow", action="append", help="Workflow names to reuse.")
    plan.add_argument("--input-1", help="Primary input path.")
    plan.add_argument("--input-2", help="Secondary input path.")
    plan.add_argument("--input-json", help="Input JSON path.")
    plan.add_argument("--probe-json", help="Probe result JSON from the shared Bio-OS helper.")
    plan.add_argument("--output-dir", help="Optional output directory.")
    plan.set_defaults(func=cmd_plan)

    summarize = subparsers.add_parser("summarize", help="Summarize an existing benchmark result directory.")
    summarize.add_argument("--source-dir", required=True, help="Directory containing benchmark outputs.")
    summarize.add_argument("--max-files", type=int, default=50, help="Maximum number of files to list.")
    summarize.add_argument("--output-dir", help="Optional output directory.")
    summarize.set_defaults(func=cmd_summarize)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
