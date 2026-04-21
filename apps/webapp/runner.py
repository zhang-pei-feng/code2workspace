"""Background one-shot execution for the minimal web API backend."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from apps.webapp.store import AppStore


def repo_root() -> Path:
    """Return the repository root for this web app."""
    return Path(__file__).resolve().parents[2]


def queue_one_shot_run(store: AppStore, session_id: str, prompt: str) -> dict:
    """Create one run and execute it in a background thread."""
    run = store.create_run(session_id, prompt)
    store.append_message(session_id, role="user", content=prompt, run_id=run.id)
    store.maybe_update_title_from_prompt(session_id, prompt)
    thread = threading.Thread(
        target=_run_one_shot,
        args=(store, session_id, run.id, prompt),
        daemon=True,
    )
    thread.start()
    return {"run_id": run.id, "status": run.status}


def _run_one_shot(store: AppStore, session_id: str, run_id: str, prompt: str) -> None:
    """Run the existing non-interactive CLI and persist the outcome."""
    store.mark_run_running(run_id)
    cmd = [
        "uv",
        "run",
        "--project",
        "libs/cli",
        "code2workspace",
        "--shell-allow-list",
        "all",
        "-n",
        prompt,
        "-q",
        "--no-mcp",
    ]
    try:
        process = subprocess.Popen(
            cmd,
            cwd=repo_root(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        message = f"Runner crashed before completion: {type(exc).__name__}: {exc}"
        store.append_message(
            session_id,
            role="assistant",
            content=message,
            run_id=run_id,
        )
        store.complete_run(
            run_id,
            status="failed",
            output=message,
            exit_code=None,
            error=message,
        )
        return

    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line)
        store.append_run_output(run_id, line)
    returncode = process.wait()
    combined = "".join(lines).strip()
    assistant_text = combined or "(empty output)"
    status = "succeeded" if returncode == 0 else "failed"
    store.append_message(
        session_id,
        role="assistant",
        content=assistant_text,
        run_id=run_id,
    )
    store.complete_run(
        run_id,
        status=status,
        output=combined,
        exit_code=returncode,
        error=(combined if returncode != 0 else None),
    )
