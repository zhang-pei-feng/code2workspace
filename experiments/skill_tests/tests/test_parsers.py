from experiments.skill_tests.parsers import (
    extract_repo_paths,
    extract_summary_lines,
    parse_subagents,
    parse_tool_invocations,
)


def test_parse_tool_invocations_extracts_subagent() -> None:
    log = "\n".join(
        [
            "🔧 Calling tool: (*) task [research-helper]",
            '🔧 Calling tool: (*) execute("python3 skills/...")',
        ]
    )

    parsed = parse_tool_invocations(log)

    assert parsed[0]["tool"] == "task"
    assert parsed[0]["subagent"] == "research-helper"
    assert parsed[1]["tool"] == "execute"
    assert parsed[1]["subagent"] is None


def test_parse_subagents_returns_all_subagent_names() -> None:
    log = "\n".join(
        [
            "🔧 Calling tool: (*) task [research-helper]",
            "🔧 Calling tool: (*) task [synthesis-helper]",
        ]
    )

    assert parse_subagents(log) == [
        "research-helper",
        "synthesis-helper",
    ]


def test_parse_subagents_reads_summary_bullets() -> None:
    log = "\n".join(
        [
            "已启动的子agent：",
            "- `research-helper`",
            "- `synthesis-helper`",
        ]
    )

    assert parse_subagents(log) == [
        "research-helper",
        "synthesis-helper",
    ]


def test_extract_summary_lines_filters_tool_lines() -> None:
    log = "\n".join(
        [
            "🔧 Calling tool: (*) task [research-helper]",
            "输出目录：results/skills/demo",
            "风险等级：Elevated",
        ]
    )

    assert extract_summary_lines(log) == [
        "输出目录：results/skills/demo",
        "风险等级：Elevated",
    ]


def test_extract_repo_paths_returns_unique_paths() -> None:
    log = (
        "Output directory: /mnt/data1/zhangpf/code2workspace/results/skills/demo/123\n"
        "Report: /mnt/data1/zhangpf/code2workspace/results/skills/demo/123/final_report.md\n"
    )

    paths = extract_repo_paths(log)

    assert str(paths[0]).endswith("/results/skills/demo/123")
    assert str(paths[1]).endswith("/results/skills/demo/123/final_report.md")
