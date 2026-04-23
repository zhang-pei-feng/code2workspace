import json
from pathlib import Path

from experiments.skill_tests.judge import (
    build_rule_score,
    judge_case,
    judge_results,
    parse_judge_output,
)


def test_build_rule_score_counts_trace_and_answer_quality(tmp_path: Path) -> None:
    answer_path = tmp_path / "demo.answer.txt"
    answer_path.write_text(
        "结论：当前信号偏低。\n\n信息来源：\n- https://example.invalid/source\n",
        encoding="utf-8",
    )
    trace_path = tmp_path / "demo.trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "tool_invocation_count": 1,
                "answer_char_count": 42,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = {
        "status": "passed",
        "answer_path": str(answer_path),
        "trace_path": str(trace_path),
        "tool_invocations": [{"tool": "fetch_url", "display": "fetch_url", "subagent": None}],
        "source_urls": ["https://example.invalid/source"],
    }

    score = build_rule_score(result)

    assert score["total"] == 20
    assert all(score["checks"].values())


def test_parse_judge_output_accepts_strict_json() -> None:
    payload = parse_judge_output(
        '{"overall_score": 77, "judge_score": 62, "rule_score": 15, '
        '"dimension_scores": {"accuracy": 25, "completeness": 16, '
        '"reasonableness": 11, "trace_rationality": 10}, '
        '"verdict": "good", "major_issues": [], "trace_findings": [], '
        '"improvement_hints": []}'
    )

    assert payload["overall_score"] == 77
    assert payload["dimension_scores"]["accuracy"] == 25


def test_judge_case_combines_rule_and_model_scores(
    tmp_path: Path, monkeypatch
) -> None:
    answer_path = tmp_path / "demo.answer.txt"
    answer_path.write_text("答案正文\n\n信息来源：\n- https://example.invalid/source\n", encoding="utf-8")
    trace_path = tmp_path / "demo.trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "tool_invocation_count": 2,
                "answer_char_count": 24,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = {
        "name": "demo-case",
        "prompt": "demo question",
        "status": "passed",
        "answer_path": str(answer_path),
        "trace_path": str(trace_path),
        "tool_invocations": [{"tool": "fetch_url", "display": "fetch_url", "subagent": None}],
        "source_urls": ["https://example.invalid/source"],
        "task_family": "trend-analysis",
        "question_type": "forecast",
        "judge_focus": ["accuracy", "trace_rationality"],
        "preferred_skills": ["planning-guide", "epietl-api"],
    }

    monkeypatch.setattr(
        "experiments.skill_tests.judge.invoke_judge_model",
        lambda prompt, model_spec="openai:gpt-5.4": json.dumps(
            {
                "overall_score": 0,
                "judge_score": 61,
                "rule_score": 0,
                "dimension_scores": {
                    "accuracy": 24,
                    "completeness": 16,
                    "reasonableness": 11,
                    "trace_rationality": 10,
                },
                "verdict": "good",
                "major_issues": [],
                "trace_findings": [],
                "improvement_hints": [],
            },
            ensure_ascii=False,
        ),
    )

    judged = judge_case(result)

    assert judged["judge_score"] == 61
    assert judged["rule_score"] == 20
    assert judged["overall_score"] == 81


def test_judge_results_writes_case_judge_files(
    tmp_path: Path, monkeypatch
) -> None:
    answer_path = tmp_path / "demo.answer.txt"
    answer_path.write_text("答案正文\n\n信息来源：\n- https://example.invalid/source\n", encoding="utf-8")
    trace_path = tmp_path / "demo.trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "tool_invocation_count": 2,
                "answer_char_count": 24,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = {
        "name": "demo-case",
        "prompt": "demo question",
        "status": "passed",
        "answer_path": str(answer_path),
        "trace_path": str(trace_path),
        "tool_invocations": [{"tool": "fetch_url", "display": "fetch_url", "subagent": None}],
        "source_urls": ["https://example.invalid/source"],
        "task_family": "trend-analysis",
        "question_type": "forecast",
        "judge_focus": ["accuracy", "trace_rationality"],
        "preferred_skills": ["planning-guide", "epietl-api"],
    }

    monkeypatch.setattr(
        "experiments.skill_tests.judge.invoke_judge_model",
        lambda prompt, model_spec="openai:gpt-5.4": json.dumps(
            {
                "overall_score": 0,
                "judge_score": 61,
                "rule_score": 0,
                "dimension_scores": {
                    "accuracy": 24,
                    "completeness": 16,
                    "reasonableness": 11,
                    "trace_rationality": 10,
                },
                "verdict": "good",
                "major_issues": [],
                "trace_findings": [],
                "improvement_hints": [],
            },
            ensure_ascii=False,
        ),
    )

    judged_results = judge_results([result], run_date="20260423")

    assert judged_results[0]["overall_score"] == 81
    judge_path = Path(judged_results[0]["judge_path"])
    assert judge_path.exists()
    payload = json.loads(judge_path.read_text(encoding="utf-8"))
    assert payload["overall_score"] == 81
