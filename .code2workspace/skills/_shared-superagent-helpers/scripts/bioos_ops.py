#!/usr/bin/env python3
"""Small shared wrappers for Bio-OS oriented skill flows."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import create_skill_run_dir, ensure_dir, write_json, write_text


DEFAULT_ENDPOINT = "https://bio-top.miracle.ac.cn"


def _tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _run_command(cmd: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {
            "ok": False,
            "command": cmd,
            "error": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _credentials_status() -> dict[str, Any]:
    return {
        "has_access_key": bool(os.environ.get("MIRACLE_ACCESS_KEY")),
        "has_secret_key": bool(os.environ.get("MIRACLE_SECRET_KEY")),
    }


def _write_result(run_dir: Path, name: str, payload: dict[str, Any]) -> None:
    write_json(run_dir / f"{name}.json", payload)
    write_text(
        run_dir / f"{name}.md",
        "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n",
    )


def cmd_probe(args: argparse.Namespace) -> int:
    payload = {
        "credentials": _credentials_status(),
        "tools": {
            "bw": _tool_exists("bw"),
            "bw_import": _tool_exists("bw_import"),
            "bw_status_check": _tool_exists("bw_status_check"),
        },
        "endpoint": args.endpoint,
    }
    if args.output_dir:
        run_dir = ensure_dir(Path(args.output_dir))
    else:
        run_dir = create_skill_run_dir("benchmark-workflow-orchestrator", "probe")
    _write_result(run_dir, "probe", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_list_workspaces(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("benchmark-workflow-orchestrator", "list-workspaces")
    ensure_dir(run_dir)
    if not _tool_exists("bw"):
        payload = {
            "ok": False,
            "reason": "bw CLI not found",
            "credentials": _credentials_status(),
        }
        _write_result(run_dir, "list_workspaces", payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    cmd = ["bw", "--endpoint", args.endpoint, "workspace", "list"]
    result = _run_command(cmd)
    _write_result(run_dir, "list_workspaces", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_submit_stub(args: argparse.Namespace) -> int:
    run_dir = Path(args.output_dir) if args.output_dir else create_skill_run_dir("benchmark-workflow-orchestrator", "submit")
    ensure_dir(run_dir)
    payload = {
        "requested_workspace": args.workspace_name,
        "requested_workflow": args.workflow_name,
        "input_json": args.input_json,
        "monitor": args.monitor,
        "credentials": _credentials_status(),
        "tools": {
            "bw": _tool_exists("bw"),
            "bw_status_check": _tool_exists("bw_status_check"),
        },
    }
    if _tool_exists("bw") and payload["credentials"]["has_access_key"] and payload["credentials"]["has_secret_key"]:
        cmd = [
            "bw",
            "--endpoint",
            args.endpoint,
            "--workspace_name",
            args.workspace_name,
            "--workflow_name",
            args.workflow_name,
            "--input_json",
            args.input_json,
        ]
        result = _run_command(cmd)
        payload["execution"] = result
    else:
        payload["execution"] = {
            "ok": False,
            "reason": "Bio-OS CLI or credentials unavailable; recorded a structured stub only.",
        }
    _write_result(run_dir, "submit_workflow", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["execution"]["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shared Bio-OS helper for project superagent skills.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Bio-OS endpoint.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="Check CLI and credential availability.")
    probe.add_argument("--output-dir", help="Optional output directory.")
    probe.set_defaults(func=cmd_probe)

    list_workspaces = subparsers.add_parser("list-workspaces", help="List workspaces via Bio-OS CLI if available.")
    list_workspaces.add_argument("--output-dir", help="Optional output directory.")
    list_workspaces.set_defaults(func=cmd_list_workspaces)

    submit_stub = subparsers.add_parser("submit-workflow", help="Submit a workflow when the local Bio-OS CLI is available.")
    submit_stub.add_argument("--workspace-name", required=True)
    submit_stub.add_argument("--workflow-name", required=True)
    submit_stub.add_argument("--input-json", required=True)
    submit_stub.add_argument("--monitor", action="store_true")
    submit_stub.add_argument("--output-dir", help="Optional output directory.")
    submit_stub.set_defaults(func=cmd_submit_stub)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
