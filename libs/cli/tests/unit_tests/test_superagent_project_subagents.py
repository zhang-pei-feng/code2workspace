"""Smoke tests for project-level subagent discovery."""

from pathlib import Path

from code2workspace_cli.subagents import list_subagents


def test_project_superagent_subagents_are_discoverable() -> None:
    project_agents_dir = Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/agents")

    subagents = list_subagents(project_agents_dir=project_agents_dir)
    by_name = {subagent["name"]: subagent for subagent in subagents}

    for name in {
        "bioos-operator",
        "epidemic-clinical-analyst",
        "epidemic-monitor-analyst",
        "epidemic-report-composer",
        "epidemic-source-cartographer",
        "epidemic-variant-analyst",
        "epidemic-web-researcher",
        "governance-operator",
        "research-lane",
        "workspace-builder",
    }:
        assert name in by_name
        assert by_name[name]["source"] == "project"
        assert Path(by_name[name]["path"]).exists()

    assert by_name["epidemic-monitor-analyst"]["allow_nested_task"] is True
    assert by_name["epidemic-monitor-analyst"]["nested_task_budget"] == 1
    assert by_name["epidemic-monitor-analyst"]["max_delegation_depth"] == 3
    assert by_name["epidemic-monitor-analyst"]["nested_subagents"] == [
        "epidemic-web-researcher"
    ]
    assert by_name["epidemic-monitor-analyst"]["nested_scope_guard"] == (
        "epidemic-warning-report"
    )
