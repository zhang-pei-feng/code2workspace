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
        / "deep-research-report"
        / "scripts"
        / "report_tool.py"
    )


def _init_run(tmp_path: Path, topic: str = "Test research topic") -> Path:
    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "init",
            "--topic",
            topic,
            "--output-dir",
            str(tmp_path / "research-run"),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    return Path(str(payload["run_dir"]))


def test_compose_builds_structured_report_and_dedupes_sources(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path, topic="Respiratory evidence synthesis")
    (run_dir / "lanes" / "01_literature.md").write_text(
        "\n".join(
            [
                "# Literature Findings",
                "",
                "Skill: academic-search",
                "Source: PubMed",
                "Source: PubMed",
                "",
                "Recent literature shows sustained immune-evasion discussion across the selected papers.",
                "Several papers also describe the tradeoff between transmissibility and neutralization escape.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "lanes" / "02_monitoring.md").write_text(
        "\n".join(
            [
                "# Monitoring Signals",
                "",
                "Skill: respiratory-disease-wide-monitor",
                "Source: WHO dashboard",
                "",
                "Official monitoring indicates continued reporting activity with cross-region variability.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "compose",
            "--run-dir",
            str(run_dir),
            "--summary",
            "Integrated summary.",
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    report_text = (run_dir / "final_report.md").read_text(encoding="utf-8")
    diagnostics = json.loads(Path(payload["diagnostics_path"]).read_text(encoding="utf-8"))

    assert "## Executive Summary" in report_text
    assert "## Literature Findings" in report_text
    assert "## Monitoring Signals" in report_text
    assert "## Cross-Lane Synthesis" in report_text
    assert report_text.count("- PubMed") == 1
    assert diagnostics["complete"] is True
    assert diagnostics["source_count"] == 2
    assert diagnostics["lane_count"] == 2
    assert diagnostics["missing_required_lanes"] == []


def test_compose_marks_incomplete_when_only_metadata_exists(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    (run_dir / "lanes" / "01_empty.md").write_text(
        "\n".join(
            [
                "# Empty Evidence",
                "",
                "Skill: academic-search",
                "Source: PubMed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "compose",
            "--run-dir",
            str(run_dir),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    report_text = (run_dir / "final_report.md").read_text(encoding="utf-8")
    diagnostics = json.loads(Path(payload["diagnostics_path"]).read_text(encoding="utf-8"))

    assert diagnostics["complete"] is False
    assert diagnostics["lane_count"] == 1
    assert diagnostics["source_count"] == 1
    assert "Missing or incomplete evidence" in report_text
