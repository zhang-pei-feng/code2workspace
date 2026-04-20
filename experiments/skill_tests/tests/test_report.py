from experiments.skill_tests.report import build_summary_zh


def test_build_summary_zh_renders_counts_and_case_sections() -> None:
    text = build_summary_zh(
        [
            {
                "name": "academic-search-positive",
                "target": "skill",
                "status": "passed",
                "conclusion_zh": "行为与输出均满足预期。",
                "log_path": "results/skill-tests/20260420/academic-search-positive.log",
                "failed_expectations": [],
                "known_issue_hits": [],
            },
            {
                "name": "epietl-api-risk-events-known-issue",
                "target": "skill",
                "status": "known_issue",
                "conclusion_zh": "命中了已知问题轨道；结果已记录但不视为通过。",
                "log_path": "results/skill-tests/20260420/epietl-api-risk-events-known-issue.log",
                "failed_expectations": [],
                "known_issue_hits": ["log:401"],
            },
        ],
        run_date="20260420",
    )

    assert "# 技能评测汇总" in text
    assert "通过：`1`" in text
    assert "已知问题：`1`" in text
    assert "## academic-search-positive" in text
    assert "## epietl-api-risk-events-known-issue" in text
