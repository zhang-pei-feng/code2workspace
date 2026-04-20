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
        / "epidemic-warning-report"
        / "scripts"
        / "epidemic_report_tool.py"
    )


def _init_run(tmp_path: Path) -> Path:
    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "init",
            "--topic",
            "测试疫情预警简报",
            "--output-dir",
            str(tmp_path / "report-run"),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    return Path(payload["run_dir"])


def test_compose_marks_complete_when_four_required_lanes_exist(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    lanes = {
        "01_official-monitoring.md": "# Official Monitoring\n\nSkill: respiratory-disease-data-fetcher\nSource: WHO dashboard\n" + ("Official monitoring evidence with detailed surveillance interpretation. " * 80) + "\n",
        "02_source-catalog.md": "# Source Catalog and Channel Context\n\nSkill: epietl-api\nSource: EpiETL channels\n" + ("Catalog evidence with source-type and coverage analysis. " * 70) + "\n",
        "03_variant-risk.md": "# Variant and Local DB Evidence\n\nSkill: virus-variation-query\nSource: local DB\n" + ("Variant evidence with explicit mutation-risk interpretation. " * 70) + "\n",
        "04_literature-clinical.md": "# Literature and Clinical Evidence\n\nSkill: academic-search\nSource: PubMed\n" + ("Literature evidence with trial-stage, vaccine-progress, and mechanistic context. " * 80) + "\n",
        "05_actions.md": "# Actions\n\nSkill: epidemic-warning-report\nSource: synthesis\n" + ("Action evidence with preparedness, sequencing, and communication guidance. " * 70) + "\n",
    }
    for name, content in lanes.items():
        (run_dir / "lanes" / name).write_text(content, encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "compose",
            "--run-dir",
            str(run_dir),
            "--risk-level",
            "Moderate",
            "--summary",
            "Test summary.",
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    diagnostics = json.loads(Path(payload["diagnostics_path"]).read_text(encoding="utf-8"))
    report_text = (run_dir / "final_report.md").read_text(encoding="utf-8")

    assert diagnostics["complete"] is True
    assert diagnostics["meets_min_report_chars"] is True
    assert diagnostics["report_char_count"] >= 5000
    assert diagnostics["source_class_count"] == 4
    assert diagnostics["missing_required_lanes"] == []
    assert "## Monitoring Overview" in report_text
    assert "## Variant / Pathogen Notes" in report_text
    assert "Source: PubMed" in report_text


def test_compose_explicitly_marks_missing_required_lane(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    (run_dir / "lanes" / "01_official-monitoring.md").write_text(
        "# Official Monitoring\n\nSkill: respiratory-disease-data-fetcher\nSource: WHO dashboard\nOfficial monitoring evidence.\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "compose",
            "--run-dir",
            str(run_dir),
            "--risk-level",
            "Elevated",
            "--summary",
            "Test summary.",
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    diagnostics = json.loads(Path(payload["diagnostics_path"]).read_text(encoding="utf-8"))
    report_text = (run_dir / "final_report.md").read_text(encoding="utf-8")

    assert diagnostics["complete"] is False
    assert "02_source-catalog.md" in diagnostics["missing_required_lanes"]
    assert "This lane is incomplete." in report_text
    assert "Missing Or Incomplete Required Lanes" in report_text


def test_record_research_step_writes_jsonl(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "record-research-step",
            "--run-dir",
            str(run_dir),
            "--lane-file",
            "01_official-monitoring.md",
            "--round",
            "1",
            "--tool",
            "fetch_url",
            "--summary",
            "Fetched one official monitoring page.",
            "--continue-search",
            "--source",
            "WHO dashboard",
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    log_path = Path(payload["research_step_log"])
    assert log_path.exists()
    line = log_path.read_text(encoding="utf-8").strip()
    assert '"tool": "fetch_url"' in line
