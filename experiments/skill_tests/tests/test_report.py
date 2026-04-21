from pathlib import Path

from experiments.skill_tests.report import (
    build_capability_snapshot_zh,
    build_summary_zh,
    extract_final_answer_from_log,
)


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


def test_extract_final_answer_from_log_strips_tool_traces() -> None:
    log = "\n".join(
        [
            "第一行回答",
            "",
            "第二行回答",
            "🔧 Calling tool: execute(\"python3 demo.py\")",
            "🔧 Calling tool: write_todos",
            "Warning: Web search is disabled",
        ]
    )

    extracted = extract_final_answer_from_log(log)

    assert "第一行回答" in extracted
    assert "第二行回答" in extracted
    assert "Calling tool:" not in extracted
    assert "Web search is disabled" not in extracted


def test_build_capability_snapshot_zh_includes_prompt_and_extracted_output(tmp_path: Path) -> None:
    log_path = tmp_path / "demo.log"
    log_path.write_text(
        "\n".join(
            [
                "这是最终回答正文。",
                "🔧 Calling tool: execute(\"python3 demo.py\")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    results = [
        {
            "name": "demo-case",
            "target": "skill",
            "status": "passed",
            "conclusion_zh": "行为与输出均满足预期。",
            "log_path": str(log_path),
            "prompt": "你好，世界？",
        }
    ]

    md = build_capability_snapshot_zh(results, run_date="20260420")

    assert "# 能力快照（输入输出）" in md
    assert "## demo-case" in md
    assert "你好，世界？" in md
    assert "这是最终回答正文。" in md
    assert "Calling tool:" not in md
