"""Run the standard one-shot task for multiple repositories."""

from __future__ import annotations

import argparse
import json
import traceback
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.oneshot.run_repo_task import (
    build_manifest_payload,
    default_output_root,
    default_workspace_root,
    write_json,
    utc_stamp,
    run_repo_task,
)
from experiments.oneshot.tasks import DEFAULT_TARGETS_FILE, build_repo_task_spec, load_repo_urls


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--targets-file",
        type=Path,
        default=DEFAULT_TARGETS_FILE,
        help="Text file with one repository URL per line",
    )
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
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of repositories to run",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue with later repositories if one run returns non-zero",
    )
    parser.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=30,
        help="Maximum runtime for each repo task before timing out",
    )
    return parser.parse_args()


def run_repo_batch(
    *,
    targets_file: Path = DEFAULT_TARGETS_FILE,
    workspace_root: Path | None = None,
    output_root: Path | None = None,
    limit: int | None = None,
    continue_on_error: bool = False,
    max_runtime_minutes: int = 30,
) -> dict[str, Any]:
    """Run a batch of one-shot repository tasks."""
    workspace = workspace_root or default_workspace_root()
    outputs = output_root or default_output_root()
    repo_urls = load_repo_urls(targets_file)
    if limit is not None:
        repo_urls = repo_urls[:limit]

    batch_dir = outputs / "_batch" / utc_stamp()
    batch_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for repo_url in repo_urls:
        try:
            result = run_repo_task(
                repo_url,
                workspace_root=workspace,
                output_root=outputs,
                max_runtime_minutes=max_runtime_minutes,
            )
        except Exception as error:
            spec = build_repo_task_spec(repo_url)
            started_at = utc_stamp()
            run_dir = batch_dir / "batch_failures" / spec.repo_name / utc_stamp()
            run_dir.mkdir(parents=True, exist_ok=True)
            log_path = run_dir / "agent.log"
            summary_path = run_dir / "summary.json"
            manifest_path = run_dir / "manifest.json"
            prompt_path = run_dir / "prompt.txt"
            prompt_path.write_text("", encoding="utf-8")
            error_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            log_path.write_text(error_trace, encoding="utf-8")
            summary = {
                "repo_url": repo_url,
                "repo_name": spec.repo_name,
                "run_dir": run_dir,
                "returncode": 1,
                "completed": False,
                "status": "batch_error",
                "summary_path": summary_path,
                "manifest_path": manifest_path,
            }
            write_json(
                summary_path,
                {
                    "returncode": 1,
                    "completed": False,
                    "status": "batch_error",
                    "max_runtime_minutes": max_runtime_minutes,
                    "target_repo": str(workspace / spec.repo_name),
                    "command": [],
                    "started_at": started_at,
                    "finished_at": utc_stamp(),
                    "error": str(error),
                },
            )
            write_json(
                manifest_path,
                build_manifest_payload(
                    spec,
                    target_repo=workspace / spec.repo_name,
                    run_dir=run_dir,
                    started_at=started_at,
                    finished_at=utc_stamp(),
                    status="batch_error",
                    max_runtime_minutes=max_runtime_minutes,
                    command=[],
                    prompt_path=prompt_path,
                    log_path=log_path,
                    summary_path=summary_path,
                    completion_judgment=None,
                ),
            )
            result = summary
        serializable = {
            **result,
            "run_dir": str(result["run_dir"]),
            "summary_path": str(result["summary_path"]),
            "manifest_path": str(result["manifest_path"]),
        }
        results.append(serializable)
        if result["returncode"] != 0 and not continue_on_error:
            break

    summary = {
        "targets_file": str(targets_file),
        "workspace_root": str(workspace),
        "output_root": str(outputs),
        "run_count": len(results),
        "continue_on_error": continue_on_error,
        "max_runtime_minutes": max_runtime_minutes,
        "results": results,
    }
    write_json(batch_dir / "batch_summary.json", summary)
    return {"batch_dir": batch_dir, "summary": summary}


def main() -> int:
    """Run the CLI entrypoint."""
    args = parse_args()
    result = run_repo_batch(
        targets_file=args.targets_file,
        workspace_root=args.workspace_root,
        output_root=args.output_root,
        limit=args.limit,
        continue_on_error=args.continue_on_error,
        max_runtime_minutes=args.max_runtime_minutes,
    )
    print(json.dumps({"batch_dir": str(result["batch_dir"]), **result["summary"]}, indent=2))
    failed = any(item["returncode"] != 0 for item in result["summary"]["results"])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
