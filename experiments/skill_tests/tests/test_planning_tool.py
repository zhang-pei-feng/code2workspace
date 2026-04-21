from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tool_path() -> Path:
    return (
        _repo_root()
        / ".code2workspace"
        / "skills"
        / "planning-guide"
        / "scripts"
        / "planning_tool.py"
    )


def _run_json(*args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(_tool_path()), *args],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _init_run(tmp_path: Path, task: str, name: str) -> Path:
    payload = _run_json("init", "--task", task, "--output-dir", str(tmp_path / name))
    return Path(str(payload["run_dir"]))


def test_classify_simple_task_keeps_generic_plan() -> None:
    payload = _run_json("classify", "--task", "整理 README 里的安装步骤")

    assert payload["domain"] == "generic"
    assert payload["complexity"] == "simple"
    assert payload["plan_mode"] == "single-step"
    assert payload["dispatch_candidate"] is None
    assert payload["recommended_skill"] is None
    assert payload["intent"]["task_shape"] == "single-scope"

def test_complex_benchmark_task_emits_soft_skill_recommendation(tmp_path: Path) -> None:
    task = "benchmark compare spades and flye with docker build and wdl"
    classify = _run_json("classify", "--task", task)

    assert classify["domain"] == "benchmark"
    assert classify["complexity"] == "complex"
    assert classify["dispatch_candidate"] == "benchmark-workflow-orchestrator"
    assert classify["recommended_skill"] == "benchmark-workflow-orchestrator"
    assert any(item["type"] == "source_option" for item in classify["recommended_sources"])

    run_dir = _init_run(tmp_path, task, "benchmark-run")
    dispatch = _run_json("dispatch", "--run-dir", str(run_dir))
    status = _run_json("status", "--run-dir", str(run_dir))

    assert dispatch["status"] == "recommended-skill-ready"
    assert dispatch["adapter"] == "benchmark-workflow-orchestrator"
    assert status["dispatch"]["adapter"] == "benchmark-workflow-orchestrator"


def test_init_writes_new_contract_fields(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path, "做一个深度研究报告，整理文献和来源链接", "research-run")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    plan_md = (run_dir / "plan.md").read_text(encoding="utf-8")

    assert "intent" in manifest
    assert "recommended_sources" in manifest
    assert "dispatch_candidate" in manifest
    assert "intent" in plan
    assert "recommended_sources" in plan
    assert "dispatch_candidate" in plan
    assert "## Planning Principles" in plan_md
    assert "## Source Options" in plan_md


def test_status_surfaces_generic_source_options_without_auto_web_or_dispatch(tmp_path: Path) -> None:
    task = "做一个深度研究报告，整理文献和来源链接"
    run_dir = _init_run(tmp_path, task, "status-run")
    status = _run_json("status", "--run-dir", str(run_dir))

    assert status["intent"]["verification_needed"] is True
    assert any(
        item["type"] == "source_option" and item["name"] == "local-repo-and-runtime"
        for item in status["recommended_sources"]
    )
    assert any(
        item["type"] == "source_option" and item["name"] == "official-docs-and-specs"
        for item in status["recommended_sources"]
    )
    assert any(
        item["type"] == "source_option" and item["name"] == "current-web-sources"
        for item in status["recommended_sources"]
    )
    assert status["dispatch_candidate"] is None
