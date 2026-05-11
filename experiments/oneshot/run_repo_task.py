"""Clone one repository and run the standard one-shot agent task."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from queue import Empty, Queue
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.oneshot.completion import (
    capture_completion_snapshot,
    completion_rubric_path,
    judge_completion,
    load_completion_rubric,
)
from experiments.oneshot.tasks import build_repo_task_prompt, build_repo_task_spec


class RepoPreparationError(RuntimeError):
    """Raised when one repository cannot be prepared for execution."""

    def __init__(self, message: str, *, returncode: int, log_path: Path) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.log_path = log_path


def utc_stamp() -> str:
    """Return a filesystem-friendly UTC timestamp."""
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def repo_root() -> Path:
    """Return the repository root for this project."""
    return Path(__file__).resolve().parents[2]


def default_workspace_root() -> Path:
    """Return the default clone directory for experiment repositories."""
    return repo_root() / ".workspaces" / "oneshot"


def default_output_root() -> Path:
    """Return the default output directory for experiment runs."""
    return repo_root() / "results" / "oneshot"


def default_max_runtime_minutes() -> int:
    """Return the default maximum runtime for one repository run."""
    return 30


def default_transient_remote_retries() -> int:
    """Return how many transient remote failures should be retried."""
    return 2


def cli_project_root() -> Path:
    """Return the absolute path to the local CLI project."""
    return repo_root() / "libs" / "cli"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON file with stable formatting."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def append_log(path: Path, content: str) -> None:
    """Append one text block to a log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def retry_log_path(log_path: Path, retry_index: int) -> Path:
    """Return the archived log path for one retry attempt."""
    return log_path.with_name(f"{log_path.stem}.retry{retry_index}{log_path.suffix}")


def remove_path(path: Path) -> None:
    """Remove one generated file or directory if it exists."""
    if not path.exists():
        return
    if path.is_dir():
        try:
            shutil.rmtree(path)
        except PermissionError:
            quarantine_path(path)
        return
    try:
        path.unlink()
    except PermissionError:
        quarantine_path(path)


def quarantine_path(path: Path) -> Path:
    """Move one stale artifact aside when direct removal is blocked."""
    suffix = f".stale.{utc_stamp()}"
    candidate = path.with_name(f"{path.name}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}{suffix}.{counter}")
        counter += 1
    path.rename(candidate)
    return candidate


def clear_generated_repo_artifacts(target_repo: Path, spec: Any) -> None:
    """Remove generated experiment artifacts before starting a fresh run."""
    generated_paths = (
        target_repo / spec.dockerfile_name,
        target_repo / spec.wdl_name,
        target_repo / "inputs.json",
        target_repo / "miniwdl_run_state",
        target_repo / "results" / "docker_test",
        target_repo / "results" / "wdl_result",
        target_repo / "results" / "wdl_file",
    )
    for path in generated_paths:
        remove_path(path)


def is_transient_remote_error(
    *,
    output: str,
    returncode: int,
    interrupted: bool,
    timed_out: bool,
) -> bool:
    """Return whether one failed run looks like a transient remote/internal error."""
    if returncode == 0 or interrupted or timed_out:
        return False
    lowered = output.lower()
    if "unexpected error (remoteexception)" not in lowered:
        return False
    return "internal error occurred" in lowered


def run_agent_command_with_retries(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path,
    max_runtime_seconds: int | None,
    target_repo: Path,
    spec: Any,
    transient_remote_retries: int = default_transient_remote_retries(),
) -> tuple[int, str, bool, bool, int, list[str]]:
    """Run the agent command and retry transient remote failures once."""
    combined_outputs: list[str] = []
    retry_logs: list[str] = []
    started = time.monotonic()

    for attempt in range(transient_remote_retries + 1):
        remaining_seconds = max_runtime_seconds
        if max_runtime_seconds is not None:
            elapsed = int(time.monotonic() - started)
            remaining_seconds = max(max_runtime_seconds - elapsed, 1)

        returncode, output, interrupted, timed_out = stream_command(
            cmd,
            cwd=cwd,
            log_path=log_path,
            max_runtime_seconds=remaining_seconds,
        )
        combined_outputs.append(output)

        if attempt >= transient_remote_retries or not is_transient_remote_error(
            output=output,
            returncode=returncode,
            interrupted=interrupted,
            timed_out=timed_out,
        ):
            return (
                returncode,
                "".join(combined_outputs),
                interrupted,
                timed_out,
                attempt,
                retry_logs,
            )

        archived_log_path = retry_log_path(log_path, attempt + 1)
        if log_path.exists():
            shutil.move(log_path, archived_log_path)
            retry_logs.append(str(archived_log_path))
        clear_generated_repo_artifacts(target_repo, spec)

    return 1, "".join(combined_outputs), False, False, transient_remote_retries, retry_logs


def summarize_result(
    spec: Any,
    *,
    target_repo: Path,
    run_dir: Path,
    started_at: str,
    finished_at: str,
    status: str,
    completed: bool,
    returncode: int,
    command: list[str],
    prompt_path: Path,
    log_path: Path,
    summary_path: Path,
    manifest_path: Path,
    max_runtime_minutes: int,
    completion_judgment: dict[str, Any] | None = None,
    retry_count: int = 0,
    retry_logs: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Write stable summary and manifest files for one run result."""
    summary: dict[str, Any] = {
        "returncode": returncode,
        "completed": completed,
        "status": status,
        "max_runtime_minutes": max_runtime_minutes,
        "target_repo": str(target_repo),
        "command": command,
        "started_at": started_at,
        "finished_at": finished_at,
        "completion_judgment": completion_judgment,
        "retry_count": retry_count,
        "retry_logs": retry_logs or [],
    }
    if error is not None:
        summary["error"] = error
    write_json(summary_path, summary)
    write_json(
        manifest_path,
        build_manifest_payload(
            spec,
            target_repo=target_repo,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            max_runtime_minutes=max_runtime_minutes,
            command=command,
            prompt_path=prompt_path,
            log_path=log_path,
            summary_path=summary_path,
            completion_judgment=completion_judgment,
            retry_count=retry_count,
            retry_logs=retry_logs,
        ),
    )
    return {
        "repo_url": spec.repo_url,
        "repo_name": spec.repo_name,
        "run_dir": run_dir,
        "returncode": returncode,
        "completed": completed,
        "status": status,
        "summary_path": summary_path,
        "manifest_path": manifest_path,
    }


def build_manifest_payload(
    spec: Any,
    *,
    target_repo: Path,
    run_dir: Path,
    started_at: str,
    status: str,
    command: list[str],
    prompt_path: Path,
    log_path: Path,
    summary_path: Path,
    completion_judgment: dict[str, Any] | None,
    max_runtime_minutes: int,
    retry_count: int = 0,
    retry_logs: list[str] | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Build one stable manifest payload."""
    payload = {
        "repo_url": spec.repo_url,
        "repo_name": spec.repo_name,
        "image_name": spec.image_name,
        "artifact_prefix": spec.artifact_prefix,
        "workspace": str(target_repo),
        "run_dir": str(run_dir),
        "started_at": started_at,
        "status": status,
        "max_runtime_minutes": max_runtime_minutes,
        "command": command,
        "prompt_file": str(prompt_path),
        "log_file": str(log_path),
        "summary_file": str(summary_path),
        "completion_rubric_file": str(completion_rubric_path()),
        "retry_count": retry_count,
        "retry_logs": retry_logs or [],
    }
    if completion_judgment is not None:
        payload["completed"] = completion_judgment["completed"]
        payload["completion_failed_checks"] = completion_judgment["failed_checks"]
    if finished_at is not None:
        payload["finished_at"] = finished_at
    return payload


def ensure_repo(repo_url: str, workspace_root: Path, *, clone_log_path: Path | None = None, attempts: int = 3) -> Path:
    """Clone the repo if missing; otherwise reuse the existing checkout."""
    spec = build_repo_task_spec(repo_url)
    repo_dir = workspace_root / spec.repo_name
    workspace_root.mkdir(parents=True, exist_ok=True)
    if repo_dir.exists() and (repo_dir / ".git").exists():
        return repo_dir
    if clone_log_path is not None:
        clone_log_path.parent.mkdir(parents=True, exist_ok=True)
        clone_log_path.write_text("", encoding="utf-8")

    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        if repo_dir.exists() and not (repo_dir / ".git").exists():
            shutil.rmtree(repo_dir)
        result = subprocess.run(
            ["git", "clone", repo_url, str(repo_dir)],
            cwd=workspace_root,
            text=True,
            capture_output=True,
        )
        if clone_log_path is not None:
            append_log(
                clone_log_path,
                f"$ git clone {repo_url} {repo_dir}\n{result.stdout}{result.stderr}\n",
            )
        if result.returncode == 0:
            return repo_dir
        last_error = subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )
        if attempt < attempts and clone_log_path is not None:
            append_log(clone_log_path, f"clone attempt {attempt} failed; retrying\n")
        time.sleep(min(attempt, 3))

    message = f"git clone failed after {attempts} attempts for {repo_url}"
    raise RepoPreparationError(
        message,
        returncode=(last_error.returncode if last_error is not None else 128),
        log_path=clone_log_path or (workspace_root / f"{spec.repo_name}_clone.log"),
    )


def _terminate_process(process: subprocess.Popen[str]) -> int:
    """Terminate one subprocess and return its final exit code."""
    process.terminate()
    try:
        return process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def stream_command(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path,
    max_runtime_seconds: int | None,
) -> tuple[int, str, bool, bool]:
    """Run one command and tee combined output to stdout and a log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        queue: Queue[str | None] = Queue()

        def enqueue_output() -> None:
            for line in process.stdout:
                queue.put(line)
            queue.put(None)

        reader = threading.Thread(target=enqueue_output, daemon=True)
        reader.start()
        started = time.monotonic()
        try:
            stream_finished = False
            while True:
                if max_runtime_seconds is not None and time.monotonic() - started > max_runtime_seconds:
                    returncode = _terminate_process(process)
                    return returncode or 124, "".join(lines), False, True
                try:
                    item = queue.get(timeout=0.5)
                except Empty:
                    if stream_finished and process.poll() is not None:
                        break
                    continue
                if item is None:
                    stream_finished = True
                    if process.poll() is not None:
                        break
                    continue
                print(item, end="", flush=True)
                log_file.write(item)
                log_file.flush()
                lines.append(item)
            returncode = process.wait()
            return returncode, "".join(lines), False, False
        except KeyboardInterrupt:
            returncode = _terminate_process(process)
            return returncode or 130, "".join(lines), True, False


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_url", help="GitHub repository URL to run")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=default_workspace_root(),
        help="Directory where target repositories are cloned",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=default_output_root(),
        help="Directory where run artifacts are written",
    )
    parser.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=default_max_runtime_minutes(),
        help="Maximum runtime for one repo task before timing out",
    )
    return parser.parse_args()


def run_repo_task(
    repo_url: str,
    *,
    workspace_root: Path | None = None,
    output_root: Path | None = None,
    max_runtime_minutes: int = default_max_runtime_minutes(),
) -> dict[str, Any]:
    """Run the end-to-end one-shot task for one repository."""
    workspace = workspace_root or default_workspace_root()
    outputs = output_root or default_output_root()
    spec = build_repo_task_spec(repo_url)
    run_dir = outputs / spec.repo_name / utc_stamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    target_repo = workspace / spec.repo_name

    prompt = build_repo_task_prompt(repo_url)
    prompt_path = run_dir / "prompt.txt"
    manifest_path = run_dir / "manifest.json"
    log_path = run_dir / "agent.log"
    summary_path = run_dir / "summary.json"
    clone_log_path = run_dir / "clone.log"
    command = [
        "uv",
        "run",
        "--project",
        str(cli_project_root()),
        "code2workspace",
        "--session-workdir-mode",
        "inherit",
        "--shell-allow-list",
        "all",
        "-n",
        prompt,
        "-q",
        "--no-mcp",
    ]
    started_at = datetime.now(tz=UTC).isoformat()

    prompt_path.write_text(prompt, encoding="utf-8")
    write_json(
        manifest_path,
        build_manifest_payload(
            spec,
            target_repo=target_repo,
            run_dir=run_dir,
            started_at=started_at,
            status="running",
            max_runtime_minutes=max_runtime_minutes,
            command=command,
            prompt_path=prompt_path,
            log_path=log_path,
            summary_path=summary_path,
            completion_judgment=None,
            retry_count=0,
            retry_logs=[],
        ),
    )

    try:
        target_repo = ensure_repo(repo_url, workspace, clone_log_path=clone_log_path)
    except RepoPreparationError as error:
        finished_at = datetime.now(tz=UTC).isoformat()
        if clone_log_path.exists():
            shutil.copyfile(clone_log_path, log_path)
        return summarize_result(
            spec,
            target_repo=target_repo,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            status="setup_failed",
            completed=False,
            returncode=error.returncode,
            command=command,
            prompt_path=prompt_path,
            log_path=log_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
            max_runtime_minutes=max_runtime_minutes,
            completion_judgment=None,
            retry_count=0,
            retry_logs=[],
            error=str(error),
        )

    rubric_text = load_completion_rubric()
    clear_generated_repo_artifacts(target_repo, spec)
    before_snapshot = capture_completion_snapshot(target_repo, spec)
    returncode, output, interrupted, timed_out, retry_count, retry_logs = run_agent_command_with_retries(
        command,
        cwd=target_repo,
        log_path=log_path,
        max_runtime_seconds=max_runtime_minutes * 60,
        target_repo=target_repo,
        spec=spec,
    )
    finished_at = datetime.now(tz=UTC).isoformat()
    completion_judgment = judge_completion(
        spec=spec,
        target_repo=target_repo,
        before=before_snapshot,
        output=output,
        returncode=returncode,
        interrupted=interrupted,
        timed_out=timed_out,
        rubric_text=rubric_text,
    )
    completed = bool(completion_judgment["completed"])
    status = "interrupted" if interrupted else ("timed_out" if timed_out else ("completed" if completed else "finished"))
    return summarize_result(
        spec,
        target_repo=target_repo,
        run_dir=run_dir,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        completed=completed,
        returncode=returncode,
        command=command,
        prompt_path=prompt_path,
        log_path=log_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        max_runtime_minutes=max_runtime_minutes,
        completion_judgment=completion_judgment,
        retry_count=retry_count,
        retry_logs=retry_logs,
    )


def main() -> int:
    """Run the CLI entrypoint."""
    args = parse_args()
    result = run_repo_task(
        args.repo_url,
        workspace_root=args.workspace_root,
        output_root=args.output_root,
        max_runtime_minutes=args.max_runtime_minutes,
    )
    print(json.dumps({**result, "run_dir": str(result["run_dir"])}, indent=2, default=str))
    return int(result["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
