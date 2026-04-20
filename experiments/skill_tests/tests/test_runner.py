from pathlib import Path

import pytest

from experiments.skill_tests.runner import (
    LiveEvalCase,
    _build_command,
    _matches,
    cases_root,
    load_case,
)


def test_load_case_reads_required_fields() -> None:
    case = load_case(cases_root() / "academic-search-positive.toml")

    assert case.target == "skill"
    assert case.name == "academic-search-positive"
    assert "PubMed" in case.expected_behaviors[1]
    assert case.allow_timeout_after_expectations is False


def test_load_case_reads_allow_timeout_flag() -> None:
    case = load_case(cases_root() / "epidemic-warning-report-behavior.toml")

    assert case.allow_timeout_after_expectations is True


def test_load_case_rejects_invalid_target(tmp_path: Path) -> None:
    case_path = tmp_path / "bad.toml"
    case_path.write_text(
        """
target = "bad-target"
name = "bad"
prompt = "hello"
required_env = []
expected_behaviors = []
expected_outputs = []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_case(case_path)


def test_matches_supports_tool_and_subagent_and_report_predicates() -> None:
    context = {
        "tool_names": ["task", "task", "execute"],
        "subagents": [
            "epidemic-monitor-analyst",
            "epidemic-clinical-analyst",
        ],
        "summary_lines": ["Output directory: /tmp/demo", "Risk level: Elevated"],
        "log_text": "hello 401 world",
        "report_final_exists": True,
        "report_char_count": 6200,
        "report_meets_min_chars": True,
        "report_lane_count": 4,
        "report_sources_count": 3,
        "report_has_risk_level": True,
        "report_complete": True,
        "report_source_class_count": 4,
        "report_missing_lane_count": 0,
        "artifact_new_run_dir": "/tmp/demo",
    }

    assert _matches("tool:task", context) is True
    assert _matches("tool-count:task>=2", context) is True
    assert _matches("subagent:epidemic-clinical-analyst", context) is True
    assert _matches("subagent-count>=2", context) is True
    assert _matches("log:401", context) is True
    assert _matches("report-final-exists", context) is True
    assert _matches("report-char-count>=5000", context) is True
    assert _matches("report-meets-min-chars", context) is True
    assert _matches("report-lane-count>=3", context) is True
    assert _matches("report-sources-count>=2", context) is True
    assert _matches("report-risk-level", context) is True
    assert _matches("report-complete", context) is True
    assert _matches("report-source-class-count>=4", context) is True
    assert _matches("report-missing-lane-count<=0", context) is True


def test_build_command_preserves_cwd_for_skill_eval_cases() -> None:
    case = LiveEvalCase(
        target="skill",
        name="demo",
        prompt="hello",
        required_env=(),
        expected_behaviors=(),
        expected_outputs=(),
        known_issues=(),
        timeout_minutes=10,
        allow_timeout_after_expectations=False,
        command=None,
        artifact_root=None,
        path=Path("/tmp/demo.toml"),
    )

    command = _build_command(case)

    assert "--session-workdir-mode" in command
    assert "inherit" in command
