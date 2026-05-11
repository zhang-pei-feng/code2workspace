from __future__ import annotations

from pathlib import Path
import time

from experiments.swebench.run_swebench_lite_pilot import (
    _run_logged_command,
    _run_agent_for_instance_with_retries,
    _run_official_evaluation_with_retries,
)


def test_run_official_evaluation_with_retries_retries_on_error_instances(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, Path]] = []

    def fake_run_official_evaluation(
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
    ) -> dict[str, object]:
        calls.append((run_id, log_path if log_path is not None else Path()))
        if len(calls) == 1:
            return {
                "resolved_ids": [],
                "completed_ids": [],
                "unresolved_ids": [],
                "error_ids": ["pylint-dev__astroid-1268"],
                "evaluation_returncode": 0,
                "evaluation_timed_out": False,
            }
        return {
            "resolved_ids": ["pylint-dev__astroid-1268"],
            "completed_ids": ["pylint-dev__astroid-1268"],
            "unresolved_ids": [],
            "error_ids": [],
            "evaluation_returncode": 0,
            "evaluation_timed_out": False,
        }

    monkeypatch.setattr(
        "experiments.swebench.run_swebench_lite_pilot._run_official_evaluation",
        fake_run_official_evaluation,
    )

    report = _run_official_evaluation_with_retries(
        tmp_path,
        dataset_name="SWE-bench/SWE-bench_Lite",
        split="dev",
        instance_ids=["pylint-dev__astroid-1268"],
        predictions_path=tmp_path / "predictions.jsonl",
        run_id="pilot-run",
        eval_max_workers=1,
        eval_timeout=1800,
        official_eval_retries=1,
    )

    assert [call[0] for call in calls] == ["pilot-run", "pilot-run-retry1"]
    assert report["resolved_ids"] == ["pylint-dev__astroid-1268"]
    assert report["evaluation_attempts"] == [
        {
            "run_id": "pilot-run",
            "resolved_instances": 0,
            "error_instances": 1,
            "evaluation_returncode": 0,
            "evaluation_timed_out": False,
        },
        {
            "run_id": "pilot-run-retry1",
            "resolved_instances": 1,
            "error_instances": 0,
            "evaluation_returncode": 0,
            "evaluation_timed_out": False,
        },
    ]
    assert calls[0][1].name == "evaluation.log"
    assert calls[1][1].name == "evaluation.retry1.log"


def test_run_official_evaluation_with_retries_stops_after_first_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def fake_run_official_evaluation(
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
    ) -> dict[str, object]:
        calls.append(run_id)
        return {
            "resolved_ids": ["marshmallow-code__marshmallow-1359"],
            "completed_ids": ["marshmallow-code__marshmallow-1359"],
            "unresolved_ids": [],
            "error_ids": [],
            "evaluation_returncode": 0,
            "evaluation_timed_out": False,
        }

    monkeypatch.setattr(
        "experiments.swebench.run_swebench_lite_pilot._run_official_evaluation",
        fake_run_official_evaluation,
    )

    report = _run_official_evaluation_with_retries(
        tmp_path,
        dataset_name="SWE-bench/SWE-bench_Lite",
        split="dev",
        instance_ids=["marshmallow-code__marshmallow-1359"],
        predictions_path=tmp_path / "predictions.jsonl",
        run_id="pilot-run",
        eval_max_workers=1,
        eval_timeout=1800,
        official_eval_retries=2,
    )

    assert calls == ["pilot-run"]
    assert report["resolved_ids"] == ["marshmallow-code__marshmallow-1359"]
    assert report["evaluation_attempts"] == [
        {
            "run_id": "pilot-run",
            "resolved_instances": 1,
            "error_instances": 0,
            "evaluation_returncode": 0,
            "evaluation_timed_out": False,
        }
    ]


def test_run_agent_for_instance_with_retries_retries_on_transient_internal_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def fake_checkout_commit(repo_dir: Path, commit: str) -> None:
        return None

    def fake_run_agent_for_instance(
        instance: dict[str, object],
        *,
        repo_dir: Path,
        instance_dir: Path,
        model_name: str,
        agent_max_runtime_minutes: int,
        use_hints: bool,
        log_suffix: str = "",
    ) -> dict[str, object]:
        calls.append(len(calls))
        if len(calls) == 1:
            return {
                "instance_id": "sqlfluff__sqlfluff-2419",
                "repo": "sqlfluff/sqlfluff",
                "base_commit": "abc",
                "patch_generated": False,
                "runtime_seconds": 10.0,
                "returncode": 1,
                "timed_out": False,
                "agent_output_tail": "RemoteException: {'error': 'InternalServerError'}",
            }
        return {
            "instance_id": "sqlfluff__sqlfluff-2419",
            "repo": "sqlfluff/sqlfluff",
            "base_commit": "abc",
            "patch_generated": True,
            "runtime_seconds": 12.0,
            "returncode": 0,
            "timed_out": False,
            "agent_output_tail": "done",
        }

    monkeypatch.setattr(
        "experiments.swebench.run_swebench_lite_pilot._checkout_commit",
        fake_checkout_commit,
    )
    monkeypatch.setattr(
        "experiments.swebench.run_swebench_lite_pilot._run_agent_for_instance",
        fake_run_agent_for_instance,
    )

    result = _run_agent_for_instance_with_retries(
        {"instance_id": "sqlfluff__sqlfluff-2419", "repo": "sqlfluff/sqlfluff", "base_commit": "abc"},
        repo_dir=tmp_path / "repo",
        instance_dir=tmp_path / "instance",
        model_name="code2workspace-pilot",
        agent_max_runtime_minutes=20,
        use_hints=True,
        agent_retries=1,
    )

    assert len(calls) == 2
    assert result["patch_generated"] is True
    assert result["agent_attempts"] == [
        {
            "attempt": 1,
            "returncode": 1,
            "patch_generated": False,
            "timed_out": False,
        },
        {
            "attempt": 2,
            "returncode": 0,
            "patch_generated": True,
            "timed_out": False,
        },
    ]


def test_run_agent_for_instance_with_retries_does_not_retry_non_transient_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def fake_checkout_commit(repo_dir: Path, commit: str) -> None:
        return None

    def fake_run_agent_for_instance(
        instance: dict[str, object],
        *,
        repo_dir: Path,
        instance_dir: Path,
        model_name: str,
        agent_max_runtime_minutes: int,
        use_hints: bool,
        log_suffix: str = "",
    ) -> dict[str, object]:
        calls.append(len(calls))
        return {
            "instance_id": "sqlfluff__sqlfluff-2419",
            "repo": "sqlfluff/sqlfluff",
            "base_commit": "abc",
            "patch_generated": False,
            "runtime_seconds": 10.0,
            "returncode": 1,
            "timed_out": False,
            "agent_output_tail": "validation failed",
        }

    monkeypatch.setattr(
        "experiments.swebench.run_swebench_lite_pilot._checkout_commit",
        fake_checkout_commit,
    )
    monkeypatch.setattr(
        "experiments.swebench.run_swebench_lite_pilot._run_agent_for_instance",
        fake_run_agent_for_instance,
    )

    result = _run_agent_for_instance_with_retries(
        {"instance_id": "sqlfluff__sqlfluff-2419", "repo": "sqlfluff/sqlfluff", "base_commit": "abc"},
        repo_dir=tmp_path / "repo",
        instance_dir=tmp_path / "instance",
        model_name="code2workspace-pilot",
        agent_max_runtime_minutes=20,
        use_hints=True,
        agent_retries=2,
    )

    assert len(calls) == 1
    assert result["patch_generated"] is False
    assert result["agent_attempts"] == [
        {
            "attempt": 1,
            "returncode": 1,
            "patch_generated": False,
            "timed_out": False,
        }
    ]


def test_run_logged_command_times_out_even_when_process_is_silent(tmp_path: Path) -> None:
    log_path = tmp_path / "silent.log"
    started = time.monotonic()
    returncode, timed_out, output = _run_logged_command(
        ["python3", "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        log_path=log_path,
        timeout_seconds=1,
    )
    elapsed = time.monotonic() - started

    assert timed_out is True
    assert returncode != 0
    assert output == ""
    assert elapsed < 4
