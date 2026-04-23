"""Run a small local SWE-bench Lite pilot and materialize reproducible artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def utc_stamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def cli_project_root() -> Path:
    return repo_root() / "libs" / "cli"


def swebench_python_path() -> Path:
    return repo_root() / ".venv-swebench" / "bin" / "python"


def load_pilot_instance_ids(path: Path) -> list[str]:
    instance_ids: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        instance_ids.append(line)
    return instance_ids


def build_prediction_row(instance_id: str, model_patch: str, *, model_name: str) -> dict[str, str]:
    return {
        "instance_id": instance_id,
        "model_name_or_path": model_name,
        "model_patch": model_patch,
    }


def write_predictions_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _load_dataset_rows(
    dataset_name: str,
    split: str,
    instance_ids: list[str],
) -> list[dict[str, Any]]:
    script = """
import json
import sys
from swebench.harness.utils import load_swebench_dataset

dataset_name = sys.argv[1]
split = sys.argv[2]
instance_ids = json.loads(sys.argv[3])
rows = [dict(row) for row in load_swebench_dataset(dataset_name, split=split, instance_ids=instance_ids)]
print(json.dumps(rows, ensure_ascii=False))
"""
    result = subprocess.run(
        [
            str(swebench_python_path()),
            "-c",
            script,
            dataset_name,
            split,
            json.dumps(instance_ids, ensure_ascii=False),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return list(json.loads(result.stdout))


def _clone_repo(repo: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", f"https://github.com/{repo}.git", str(destination)],
        check=True,
        text=True,
    )


def _checkout_commit(repo_dir: Path, commit: str) -> None:
    subprocess.run(["git", "checkout", commit], cwd=repo_dir, check=True, text=True)


def _run_logged_command(
    command: list[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_seconds: int | None = None,
) -> tuple[int, bool, str]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    timed_out = False
    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as handle:
        try:
            for line in process.stdout:
                lines.append(line)
                handle.write(line)
                handle.flush()
                if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
                    timed_out = True
                    process.terminate()
                    break
        finally:
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
    return returncode, timed_out, "".join(lines)


def _capture_patch(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=repo_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def _build_instance_prompt(instance: dict[str, Any], *, use_hints: bool) -> str:
    fail_to_pass = instance.get("FAIL_TO_PASS", [])
    if isinstance(fail_to_pass, str):
        fail_to_pass = json.loads(fail_to_pass)
    hints = str(instance.get("hints_text", "")).strip()
    sections = [
        "你现在在一个已经 checkout 到 benchmark base commit 的 Git 仓库里工作。",
        "目标：根据下面的 issue 描述修复代码，并把真实代码改动保留在当前工作树中。",
        "要求：",
        "- 只修改当前仓库。",
        "- 优先做最小正确修复，不要做无关重构。",
        "- 尽量运行与问题最相关的测试。",
        "- 不要提交 commit；最后需要保留可导出的 git diff。",
        "",
        "Issue 描述：",
        str(instance.get("problem_statement", "")).strip(),
        "",
        "Benchmark 提供的 FAIL_TO_PASS 测试：",
        *(f"- {item}" for item in fail_to_pass),
    ]
    if use_hints and hints:
        sections.extend(
            [
                "",
                "Benchmark 提供的 hints / 讨论：",
                hints,
            ]
        )
    sections.extend(
        [
            "",
            "完成标准：",
            "- 代码修改已经落在工作树里。",
            "- 如果你运行了测试，请在最终答复里简要说明关键测试。",
            "- 不要只给解释；必须留下实际 patch。",
        ]
    )
    return "\n".join(sections).strip() + "\n"


def _run_agent_for_instance(
    instance: dict[str, Any],
    *,
    repo_dir: Path,
    instance_dir: Path,
    model_name: str,
    agent_max_runtime_minutes: int,
    use_hints: bool,
    log_suffix: str = "",
) -> dict[str, Any]:
    prompt = _build_instance_prompt(instance, use_hints=use_hints)
    instance_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = instance_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
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
    returncode, timed_out, output = _run_logged_command(
        command,
        cwd=repo_dir,
        log_path=instance_dir / f"agent{log_suffix}.log",
        timeout_seconds=agent_max_runtime_minutes * 60,
    )
    finished_at = datetime.now(tz=UTC).isoformat()
    patch = _capture_patch(repo_dir)
    patch_path = instance_dir / "patch.diff"
    patch_path.write_text(patch, encoding="utf-8")
    instance_result = {
        "instance_id": str(instance["instance_id"]),
        "repo": str(instance["repo"]),
        "base_commit": str(instance["base_commit"]),
        "patch_generated": bool(patch.strip()),
        "runtime_seconds": round(
            datetime.fromisoformat(finished_at).timestamp() - datetime.fromisoformat(started_at).timestamp(),
            1,
        ),
        "returncode": returncode,
        "timed_out": timed_out,
        "started_at": started_at,
        "finished_at": finished_at,
        "prompt_path": str(prompt_path),
        "patch_path": str(patch_path),
        "model_name_or_path": model_name,
        "agent_output_tail": output[-4000:],
        "fail_to_pass": instance.get("FAIL_TO_PASS", []),
        "used_hints_text": bool(use_hints and str(instance.get("hints_text", "")).strip()),
    }
    write_json(instance_dir / "instance_result.json", instance_result)
    return instance_result


def _is_transient_agent_failure(result: dict[str, Any]) -> bool:
    if result.get("patch_generated") or result.get("timed_out"):
        return False
    output = str(result.get("agent_output_tail", ""))
    transient_markers = [
        "RemoteException",
        "InternalServerError",
        "RemoteProtocolError",
        "APIError",
    ]
    return any(marker in output for marker in transient_markers)


def _run_agent_for_instance_with_retries(
    instance: dict[str, Any],
    *,
    repo_dir: Path,
    instance_dir: Path,
    model_name: str,
    agent_max_runtime_minutes: int,
    use_hints: bool,
    agent_retries: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    final_result: dict[str, Any] | None = None

    for retry_index in range(max(0, agent_retries) + 1):
        _checkout_commit(repo_dir, str(instance["base_commit"]))
        log_suffix = "" if retry_index == 0 else f".retry{retry_index}"
        result = _run_agent_for_instance(
            instance,
            repo_dir=repo_dir,
            instance_dir=instance_dir,
            model_name=model_name,
            agent_max_runtime_minutes=agent_max_runtime_minutes,
            use_hints=use_hints,
            log_suffix=log_suffix,
        )
        attempts.append(
            {
                "attempt": retry_index + 1,
                "returncode": int(result.get("returncode", 0)),
                "patch_generated": bool(result.get("patch_generated")),
                "timed_out": bool(result.get("timed_out")),
            }
        )
        final_result = result
        if not _is_transient_agent_failure(result):
            break

    assert final_result is not None
    final_result["agent_attempts"] = attempts
    write_json(instance_dir / "instance_result.json", final_result)
    return final_result


def _load_run_report(run_dir: Path, run_id: str) -> dict[str, Any]:
    candidates = sorted(run_dir.glob(f"*.{run_id}.json"))
    if not candidates:
        raise FileNotFoundError(f"Could not find run report for {run_id} in {run_dir}")
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def _run_official_evaluation(
    run_dir: Path,
    *,
    dataset_name: str,
    split: str,
    instance_ids: list[str],
    predictions_path: Path,
    run_id: str,
    eval_max_workers: int,
    eval_timeout: int,
    log_path: Path | None = None,
) -> dict[str, Any]:
    command = [
        str(swebench_python_path()),
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--split",
        split,
        "--instance_ids",
        *instance_ids,
        "--predictions_path",
        str(predictions_path),
        "--max_workers",
        str(eval_max_workers),
        "--timeout",
        str(eval_timeout),
        "--run_id",
        run_id,
        "--namespace",
        "none",
    ]
    returncode, timed_out, _ = _run_logged_command(
        command,
        cwd=run_dir,
        log_path=log_path or (run_dir / "evaluation.log"),
        timeout_seconds=eval_timeout * max(1, len(instance_ids)) + 600,
    )
    report = _load_run_report(run_dir, run_id)
    report["evaluation_returncode"] = returncode
    report["evaluation_timed_out"] = timed_out
    return report


def _should_retry_official_evaluation(report: dict[str, Any]) -> bool:
    return bool(report.get("error_ids")) and not bool(report.get("resolved_ids"))


def _run_official_evaluation_with_retries(
    run_dir: Path,
    *,
    dataset_name: str,
    split: str,
    instance_ids: list[str],
    predictions_path: Path,
    run_id: str,
    eval_max_workers: int,
    eval_timeout: int,
    official_eval_retries: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    final_report: dict[str, Any] | None = None

    for retry_index in range(max(0, official_eval_retries) + 1):
        attempt_run_id = run_id if retry_index == 0 else f"{run_id}-retry{retry_index}"
        log_path = (
            run_dir / "evaluation.log"
            if retry_index == 0
            else run_dir / f"evaluation.retry{retry_index}.log"
        )
        report = _run_official_evaluation(
            run_dir,
            dataset_name=dataset_name,
            split=split,
            instance_ids=instance_ids,
            predictions_path=predictions_path,
            run_id=attempt_run_id,
            eval_max_workers=eval_max_workers,
            eval_timeout=eval_timeout,
            log_path=log_path,
        )
        attempts.append(
            {
                "run_id": attempt_run_id,
                "resolved_instances": len(report.get("resolved_ids", [])),
                "error_instances": len(report.get("error_ids", [])),
                "evaluation_returncode": report.get("evaluation_returncode"),
                "evaluation_timed_out": bool(report.get("evaluation_timed_out")),
            }
        )
        final_report = report
        if not _should_retry_official_evaluation(report):
            break

    assert final_report is not None
    final_report["evaluation_attempts"] = attempts
    return final_report


def _merge_evaluation_payload(
    instance_results: list[dict[str, Any]],
    report: dict[str, Any],
) -> dict[str, Any]:
    resolved_ids = set(report.get("resolved_ids", []))
    completed_ids = set(report.get("completed_ids", []))
    unresolved_ids = set(report.get("unresolved_ids", []))
    error_ids = set(report.get("error_ids", []))
    return {
        "report": report,
        "instances": [
            {
                **result,
                "resolved": result["instance_id"] in resolved_ids,
                "completed": result["instance_id"] in completed_ids,
                "unresolved": result["instance_id"] in unresolved_ids,
                "error": result["instance_id"] in error_ids,
            }
            for result in instance_results
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-name",
        default="SWE-bench/SWE-bench_Lite",
    )
    parser.add_argument(
        "--split",
        default="dev",
    )
    parser.add_argument(
        "--pilot-instances",
        type=Path,
        default=repo_root() / "experiments" / "swebench" / "pilot_instances.txt",
    )
    parser.add_argument(
        "--instance-limit",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=repo_root() / ".workspaces" / "swebench-lite-pilot",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=repo_root() / "results" / "swebench-lite-pilot" / "runs",
    )
    parser.add_argument(
        "--model-name",
        default="code2workspace-pilot",
    )
    parser.add_argument(
        "--agent-max-runtime-minutes",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--agent-retries",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--eval-timeout",
        type=int,
        default=1800,
    )
    parser.add_argument(
        "--eval-max-workers",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--official-eval-retries",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--use-hints",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--keep-existing-workspaces",
        action="store_true",
        default=False,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    all_instance_ids = load_pilot_instance_ids(args.pilot_instances)
    if args.instance_limit is not None:
        all_instance_ids = all_instance_ids[: args.instance_limit]
    rows = _load_dataset_rows(args.dataset_name, args.split, all_instance_ids)

    run_id = utc_stamp()
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    instance_results: list[dict[str, Any]] = []
    predictions: list[dict[str, str]] = []

    manifest = {
        "run_id": run_id,
        "dataset_name": args.dataset_name,
        "split": args.split,
        "subset_name": args.split,
        "instance_ids": [row["instance_id"] for row in rows],
        "model_name": args.model_name,
        "agent_max_runtime_minutes": args.agent_max_runtime_minutes,
        "agent_retries": args.agent_retries,
        "eval_timeout": args.eval_timeout,
        "eval_max_workers": args.eval_max_workers,
        "official_eval_retries": args.official_eval_retries,
        "use_hints_text": args.use_hints,
        "notes": f"pilot subset; max_workers={args.eval_max_workers}",
    }
    write_json(run_dir / "manifest.json", manifest)

    for row in rows:
        instance_id = str(row["instance_id"])
        instance_dir = run_dir / "instances" / instance_id
        repo_dir = args.workspace_root / instance_id / "repo"
        if repo_dir.exists() and not args.keep_existing_workspaces:
            shutil.rmtree(repo_dir.parent)
        if not repo_dir.exists():
            _clone_repo(str(row["repo"]), repo_dir)
        result = _run_agent_for_instance_with_retries(
            row,
            repo_dir=repo_dir,
            instance_dir=instance_dir,
            model_name=args.model_name,
            agent_max_runtime_minutes=args.agent_max_runtime_minutes,
            use_hints=args.use_hints,
            agent_retries=args.agent_retries,
        )
        instance_results.append(result)
        patch = Path(result["patch_path"]).read_text(encoding="utf-8")
        predictions.append(
            build_prediction_row(instance_id, patch, model_name=args.model_name)
        )

    predictions_path = run_dir / "predictions.jsonl"
    write_predictions_jsonl(predictions_path, predictions)

    eval_run_id = f"swebench-pilot-{run_id}"
    report = _run_official_evaluation_with_retries(
        run_dir,
        dataset_name=args.dataset_name,
        split=args.split,
        instance_ids=[row["instance_id"] for row in rows],
        predictions_path=predictions_path,
        run_id=eval_run_id,
        eval_max_workers=args.eval_max_workers,
        eval_timeout=args.eval_timeout,
        official_eval_retries=args.official_eval_retries,
    )
    evaluation_payload = _merge_evaluation_payload(instance_results, report)
    write_json(run_dir / "evaluation_payload.json", evaluation_payload)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "instance_count": len(rows),
                "predictions_path": str(predictions_path),
                "report_resolved": len(report.get("resolved_ids", [])),
                "report_errors": len(report.get("error_ids", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
