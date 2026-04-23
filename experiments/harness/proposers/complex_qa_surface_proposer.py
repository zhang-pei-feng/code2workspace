"""Local proposer command for the complex QA harness."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def main() -> int:
    workspace = Path(os.environ["CODE2WORKSPACE_HARNESS_WORKSPACE"])
    repo_root = Path(os.environ["CODE2WORKSPACE_HARNESS_REPO_ROOT"])
    prompt = (
        "Read ./task.md first. Then inspect ./surface_manifest.json, ./train_summary.json, "
        "and the files under ./train_cases/. Edit only files under ./current and ./proposal.md. "
        "Your goal is to improve answer accuracy, completeness, reasonableness, and trace "
        "rationality for the visible train cases without hardcoding single-case hacks. "
        "Keep edits concise and coherent. Stop as soon as ./current and ./proposal.md are updated."
    )
    env = os.environ.copy()
    env["CODE2WORKSPACE_CLI_DISABLE_UPDATE_CHECK"] = "1"
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(repo_root / "libs" / "cli"),
            "code2workspace",
            "--session-workdir-mode",
            "inherit",
            "--shell-allow-list",
            "all",
            "-n",
            prompt,
            "-q",
            "--no-mcp",
        ],
        cwd=workspace,
        env=env,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
