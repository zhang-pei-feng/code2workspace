import json
from pathlib import Path
import subprocess

import pytest

from experiments.skill_tests.runner import (
    LiveEvalCase,
    _build_command,
    _matches,
    cases_root,
    load_batch_cases,
    load_case,
    run_case,
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


def test_load_case_reads_complex_qa_metadata(tmp_path: Path) -> None:
    case_path = tmp_path / "complex.toml"
    case_path.write_text(
        """
target = "question"
name = "complex-demo"
prompt = "demo"
required_env = []
expected_behaviors = []
expected_outputs = []
task_family = "trend-analysis"
question_type = "forecast"
preferred_skills = ["planning-guide", "epietl-api"]
source_hints = ["GISAID", "EpiETL"]
source_urls = ["https://example.invalid/a"]
judge_focus = ["accuracy", "trace_rationality"]
prior_case_refs = ["covid-monitoring-08-may-mainland-dominant-lineage"]
weight = 2.0
""".strip()
        + "\n",
        encoding="utf-8",
    )

    case = load_case(case_path)

    assert case.task_family == "trend-analysis"
    assert case.question_type == "forecast"
    assert case.preferred_skills == ("planning-guide", "epietl-api")
    assert case.source_urls == ("https://example.invalid/a",)
    assert case.judge_focus == ("accuracy", "trace_rationality")
    assert case.prior_case_refs == ("covid-monitoring-08-may-mainland-dominant-lineage",)
    assert case.weight == 2.0


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
        task_family=None,
        question_type=None,
        preferred_skills=(),
        source_hints=(),
        source_urls=(),
        judge_focus=(),
        prior_case_refs=(),
        weight=1.0,
    )

    command = _build_command(case)

    assert "--session-workdir-mode" in command
    assert "inherit" in command


def test_load_batch_cases_reads_case_names_from_markdown(tmp_path: Path) -> None:
    batch_file = tmp_path / "batch.md"
    batch_file.write_text(
        "\n".join(
            [
                "# Demo Batch",
                "",
                "- `academic-search-positive.toml`: question one",
                "- `epietl-api-channels-positive.toml`: question two",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_batch_cases(batch_file)

    assert [case.path.name for case in cases] == [
        "academic-search-positive.toml",
        "epietl-api-channels-positive.toml",
    ]


def test_run_case_writes_to_custom_output_root_and_extracts_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = LiveEvalCase(
        target="question",
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
        path=tmp_path / "demo.toml",
        task_family=None,
        question_type=None,
        preferred_skills=(),
        source_hints=(),
        source_urls=(),
        judge_focus=(),
        prior_case_refs=(),
        weight=1.0,
    )

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(
            args=kwargs.get("args", args[0] if args else []),
            returncode=0,
            stdout="最终回答第一行\n最终回答第二行\n",
            stderr="",
        )

    monkeypatch.setattr("experiments.skill_tests.runner.subprocess.run", fake_run)

    result = run_case(
        case,
        run_date="20260421",
        output_root=tmp_path / "runs" / "batch-a",
    )

    assert result["log_path"].startswith(str(tmp_path / "runs" / "batch-a" / "20260421"))
    assert result["answer_path"].endswith("demo.answer.txt")
    assert result["trace_path"].endswith("demo.trace.json")
    assert Path(result["answer_path"]).read_text(encoding="utf-8").strip().startswith(
        "最终回答第一行"
    )


def test_run_case_writes_trace_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = LiveEvalCase(
        target="question",
        name="trace-demo",
        prompt="hello",
        required_env=(),
        expected_behaviors=(),
        expected_outputs=(),
        known_issues=(),
        timeout_minutes=10,
        allow_timeout_after_expectations=False,
        command=None,
        artifact_root=None,
        path=tmp_path / "trace-demo.toml",
        task_family="trend-analysis",
        question_type="forecast",
        preferred_skills=(),
        source_hints=(),
        source_urls=(),
        judge_focus=(),
        prior_case_refs=(),
        weight=1.0,
    )

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(
            args=kwargs.get("args", args[0] if args else []),
            returncode=0,
            stdout="最终回答\n🔧 Calling tool: fetch_url\n",
            stderr="",
        )

    monkeypatch.setattr("experiments.skill_tests.runner.subprocess.run", fake_run)

    result = run_case(
        case,
        run_date="20260421",
        output_root=tmp_path / "runs" / "batch-a",
    )

    trace_path = Path(result["trace_path"])
    assert trace_path.exists()
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["case_name"] == "trace-demo"
    assert payload["tool_invocation_count"] == 1
    assert payload["answer_char_count"] >= 1
    assert payload["tool_names"] == ["fetch_url"]


def test_run_case_nonzero_returncode_becomes_runner_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = LiveEvalCase(
        target="question",
        name="demo-error",
        prompt="hello",
        required_env=(),
        expected_behaviors=(),
        expected_outputs=(),
        known_issues=(),
        timeout_minutes=10,
        allow_timeout_after_expectations=False,
        command=None,
        artifact_root=None,
        path=tmp_path / "demo-error.toml",
        task_family=None,
        question_type=None,
        preferred_skills=(),
        source_hints=(),
        source_urls=(),
        judge_focus=(),
        prior_case_refs=(),
        weight=1.0,
    )

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return subprocess.CompletedProcess(
            args=kwargs.get("args", args[0] if args else []),
            returncode=1,
            stdout="Unexpected error (RemoteException): boom\n",
            stderr="",
        )

    monkeypatch.setattr("experiments.skill_tests.runner.subprocess.run", fake_run)

    result = run_case(
        case,
        run_date="20260421",
        output_root=tmp_path / "runs" / "batch-a",
    )

    assert result["status"] == "runner_error"
    assert result["returncode"] == 1
