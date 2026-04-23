"""Smoke tests for project-level subagent discovery."""

from pathlib import Path

from code2workspace_cli.subagents import list_subagents


def test_project_superagent_subagents_are_discoverable() -> None:
    project_agents_dir = Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/agents")

    subagents = list_subagents(project_agents_dir=project_agents_dir)
    by_name = {subagent["name"]: subagent for subagent in subagents}

    for name in {
        "governance-operator",
        "report-researcher",
        "report-synthesizer",
        "report-web-researcher",
        "workspace-builder",
    }:
        assert name in by_name
        assert by_name[name]["source"] == "project"
        assert Path(by_name[name]["path"]).exists()

    assert "bioos-operator" not in by_name

    assert by_name["report-researcher"]["allow_nested_task"] is True
    assert by_name["report-researcher"]["nested_task_budget"] == 1
    assert by_name["report-researcher"]["max_delegation_depth"] == 3
    assert by_name["report-researcher"]["nested_subagents"] == [
        "report-web-researcher"
    ]
    assert by_name["report-researcher"]["nested_scope_guard"] == (
        "multi-source-report"
    )
