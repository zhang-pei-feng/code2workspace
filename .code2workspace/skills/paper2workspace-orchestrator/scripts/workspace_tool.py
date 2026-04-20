#!/usr/bin/env python3
"""Create and validate paper2workspace run layouts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED_HELPER_DIR = Path(__file__).resolve().parents[2] / "_shared-superagent-helpers" / "scripts"
if str(SHARED_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_HELPER_DIR))

from common import create_skill_run_dir, ensure_dir, write_json, write_text


def _required_phase1_files(run_dir: Path) -> list[Path]:
    return [
        run_dir / "results" / "docker_test",
        run_dir / "logs" / "phase1.log",
    ]


def _required_completion_files(run_dir: Path) -> list[Path]:
    return [
        run_dir / "results" / "docker_test",
        run_dir / "results" / "wdl_file",
        run_dir / "results" / "wdl_result",
        run_dir / "logs" / "phase2.log",
    ]


def cmd_init(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("paper2workspace-orchestrator", args.repo)
    ensure_dir(run_dir / "results" / "docker_test")
    ensure_dir(run_dir / "results" / "wdl_file")
    ensure_dir(run_dir / "results" / "wdl_result")
    ensure_dir(run_dir / "logs")
    write_json(run_dir / "manifest.json", {"repo": args.repo, "run_dir": str(run_dir)})
    write_text(run_dir / "README.md", f"# Paper2Workspace Run\n\n- repo: `{args.repo}`\n")
    print(json.dumps({"run_dir": str(run_dir)}, ensure_ascii=False, indent=2))
    return 0


def cmd_phase2_ready(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    payload = {
        "run_dir": str(run_dir),
        "missing": [str(path) for path in _required_phase1_files(run_dir) if not path.exists()],
    }
    payload["ready"] = not payload["missing"]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


def cmd_completion(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    payload = {
        "run_dir": str(run_dir),
        "missing": [str(path) for path in _required_completion_files(run_dir) if not path.exists()],
    }
    payload["completed"] = not payload["missing"]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["completed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paper2workspace run scaffolding tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a fresh run directory.")
    init.add_argument("--repo", required=True)
    init.add_argument("--output-dir")
    init.set_defaults(func=cmd_init)

    phase2_ready = subparsers.add_parser("phase2-ready", help="Check whether phase 2 may start.")
    phase2_ready.add_argument("--run-dir", required=True)
    phase2_ready.set_defaults(func=cmd_phase2_ready)

    completion = subparsers.add_parser("completion", help="Check whether the run has all completion artifacts.")
    completion.add_argument("--run-dir", required=True)
    completion.set_defaults(func=cmd_completion)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
