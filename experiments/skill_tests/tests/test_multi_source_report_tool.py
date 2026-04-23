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
        / "multi-source-report"
        / "scripts"
        / "report_tool.py"
    )


def _init_run(
    tmp_path: Path,
    *,
    topic: str = "Test multi-source report",
    report_mode: str = "general",
    min_report_chars: int = 1000,
) -> Path:
    completed = subprocess.run(
        [
            sys.executable,
            str(_tool_path()),
            "init",
            "--topic",
            topic,
            "--report-mode",
            report_mode,
            "--min-report-chars",
            str(min_report_chars),
            "--output-dir",
            str(tmp_path / "report-run"),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    return Path(str(payload["run_dir"]))


def test_compose_builds_structured_general_report_and_dedupes_sources(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path, topic="Respiratory evidence synthesis")
    lanes = {
        "01_monitoring.md": "# Monitoring And Operational Evidence\n\nSkill: respiratory-disease-wide-monitor\nSource: WHO dashboard\nSource: WHO dashboard\n"
        + ("Official monitoring indicates continued reporting activity with cross-region variability and concrete operational signals. " * 30)
        + "\n",
        "02_source-catalog.md": "# Source Catalog And Coverage Evidence\n\nSkill: epietl-api\nSource: EpiETL channels\n"
        + ("Catalog evidence explains source types, channel coverage, and gaps in regional visibility for the monitored topic. " * 28)
        + "\n",
        "03_local-data.md": "# Local Structured Data Or Database Evidence\n\nSkill: virus-variation-query\nSource: local DB\n"
        + ("Local structured data shows how curated records and mutation-linked entries should be interpreted cautiously but usefully. " * 28)
        + "\n",
        "04_literature-web.md": "# Literature, Technical, And Web Evidence\n\nSkill: academic-search\nSource: PubMed\n"
        + ("Literature evidence adds mechanistic interpretation, vaccine progress, and technical context that monitoring alone cannot supply. " * 30)
        + "\n",
        "05_synthesis.md": "# Synthesis And Recommendations\n\nSkill: multi-source-report\nSource: synthesized lane evidence\n"
        + ("Cross-source synthesis compares agreement, disagreement, and practical implications for the intended audience. " * 24)
        + "\n",
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
            "--summary",
            "Integrated summary with source-backed conclusions [1][2].",
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
    assert "## Monitoring And Operational Evidence" in report_text
    assert "## Cross-Source Synthesis" in report_text
    assert "## Sources" in report_text
    assert "## Risk Or Severity Framing" not in report_text
    assert report_text.count("WHO dashboard") >= 1
    assert diagnostics["complete"] is True
    assert diagnostics["source_count"] >= 5
    assert diagnostics["lane_count"] == 5
    assert diagnostics["missing_required_lanes"] == []


def test_init_defaults_to_long_form_tables_manifest(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path, min_report_chars=5000)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["min_report_chars"] == 5000
    assert manifest["prefer_tables"] is True
    assert manifest["max_tables"] == 3


def test_compose_renders_key_data_tables_when_valid_candidates_exist(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path, min_report_chars=800)
    lanes = {
        "01_monitoring.md": "\n".join(
            [
                "# Monitoring And Operational Evidence",
                "",
                "Skill: respiratory-disease-wide-monitor",
                "Source: WHO dashboard",
                "",
                "Monitoring evidence shows recent movement across several respiratory pathogens.",
                "",
                "Table Candidate: Global Respiratory Snapshot",
                "Metric: COVID-19 cases",
                "Value: 26306",
                "Unit: cases",
                "Time: 2026-03",
                "Scope: China",
                "Source: China CDC monthly report",
                "Note: Low-level fluctuation.",
                "",
                "Table Candidate: Global Respiratory Snapshot",
                "Metric: Influenza positivity",
                "Value: 15.3",
                "Unit: %",
                "Time: 2026 week 15",
                "Scope: China sentinel outpatient",
                "Source: China CDC influenza weekly report",
                "Note: Down from prior week.",
            ]
        )
        + "\n",
        "02_source-catalog.md": "# Source Catalog And Coverage Evidence\n\nSkill: epietl-api\nSource: EpiETL channels\nCoverage and provenance evidence.\n",
        "03_local-data.md": "# Local Structured Data Or Database Evidence\n\nSkill: virus-variation-query\nSource: local DB\nStructured local evidence.\n",
        "04_literature-web.md": "# Literature, Technical, And Web Evidence\n\nSkill: academic-search\nSource: PubMed\nSupporting literature evidence.\n",
        "05_synthesis.md": "# Synthesis And Recommendations\n\nSkill: multi-source-report\nSource: synthesized lane evidence\nSynthesis evidence.\n",
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
            "--summary",
            "Integrated summary [1].",
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

    assert "## Key Data Tables" in report_text
    assert "| Metric | Value | Unit | Time | Scope | Source | Note |" in report_text
    assert "Global Respiratory Snapshot" in report_text
    assert diagnostics["table_candidate_count"] == 2
    assert diagnostics["table_rows_used"] == 2
    assert diagnostics["table_rows_rejected"] == 0
    assert diagnostics["table_count"] == 1


def test_compose_reports_when_no_reliable_numeric_table_can_be_built(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path, min_report_chars=800)
    lanes = {
        "01_monitoring.md": "\n".join(
            [
                "# Monitoring And Operational Evidence",
                "",
                "Skill: respiratory-disease-data-fetcher",
                "Source: WHO dashboard",
                "",
                "Monitoring evidence exists but the numeric fragment is incomplete.",
                "",
                "Table Candidate: Weak Numeric Fragment",
                "Metric: RSV positivity",
                "Value: 2.6",
                "Unit: %",
                "Scope: outpatient",
                "Note: Missing time and row-level source.",
            ]
        )
        + "\n",
        "02_source-catalog.md": "# Source Catalog And Coverage Evidence\n\nSkill: epietl-api\nSource: EpiETL channels\nCoverage and provenance evidence.\n",
        "03_local-data.md": "# Local Structured Data Or Database Evidence\n\nSkill: virus-variation-query\nSource: local DB\nStructured local evidence.\n",
        "04_literature-web.md": "# Literature, Technical, And Web Evidence\n\nSkill: academic-search\nSource: PubMed\nSupporting literature evidence.\n",
        "05_synthesis.md": "# Synthesis And Recommendations\n\nSkill: multi-source-report\nSource: synthesized lane evidence\nSynthesis evidence.\n",
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
            "--summary",
            "Integrated summary [1].",
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

    assert "## Key Data Tables" in report_text
    assert "No reliable numeric table could be produced" in report_text
    assert diagnostics["table_candidate_count"] == 1
    assert diagnostics["table_rows_used"] == 0
    assert diagnostics["table_rows_rejected"] == 1
    assert diagnostics["table_count"] == 0
    assert diagnostics["table_rejection_reasons"]


def test_compose_includes_risk_section_only_for_risk_reports(tmp_path: Path) -> None:
    run_dir = _init_run(
        tmp_path,
        topic="Respiratory risk briefing",
        report_mode="risk",
    )
    for name in (
        "01_monitoring.md",
        "02_source-catalog.md",
        "03_local-data.md",
        "04_literature-web.md",
    ):
        (run_dir / "lanes" / name).write_text(
            f"# {name}\n\nSkill: demo-skill\nSource: demo-source\n" + ("Evidence narrative. " * 80) + "\n",
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
            "Risk-oriented summary [1].",
            "--risk-level",
            "Elevated",
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

    assert "## Risk Or Severity Framing" in report_text
    assert "- Risk level: `Elevated`" in report_text
    assert diagnostics["report_mode"] == "risk"
    assert diagnostics["risk_level"] == "Elevated"


def test_compose_marks_incomplete_when_only_metadata_exists(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    (run_dir / "lanes" / "01_monitoring.md").write_text(
        "\n".join(
            [
                "# Monitoring And Operational Evidence",
                "",
                "Skill: respiratory-disease-data-fetcher",
                "Source: WHO dashboard",
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
    assert "02_source-catalog.md" in diagnostics["missing_required_lanes"]
    assert "This lane is incomplete." in report_text


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
            "01_monitoring.md",
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
