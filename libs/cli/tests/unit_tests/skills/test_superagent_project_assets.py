"""Smoke tests for the project-level superagent skills added to code2workspace."""

from pathlib import Path

from code2workspace_cli.skills.load import list_skills


def test_project_superagent_skills_are_discoverable() -> None:
    project_skills_dir = Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills")

    skills = list_skills(project_skills_dir=project_skills_dir)
    by_name = {skill["name"]: skill for skill in skills}

    for name in {
        "academic-search",
        "benchmark-workflow-orchestrator",
        "data-governance-ops",
        "deep-research-report",
        "epidemic-warning-report",
        "epietl-api",
        "paper2workspace-orchestrator",
        "respiratory-disease-data-fetcher",
        "respiratory-disease-wide-monitor",
        "virus-variation-query",
    }:
        assert name in by_name
        assert by_name[name]["source"] == "project"
        assert Path(by_name[name]["path"]).exists()


def test_shared_helper_directory_is_not_discoverable_as_skill() -> None:
    project_skills_dir = Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills")

    skills = list_skills(project_skills_dir=project_skills_dir)
    skill_names = {skill["name"] for skill in skills}

    assert "_shared-superagent-helpers" not in skill_names


def test_superagent_scripts_expose_help() -> None:
    scripts = [
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/_shared-superagent-helpers/scripts/bioos_ops.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/data-governance-ops/scripts/governance_ops.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/deep-research-report/scripts/report_tool.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/epidemic-warning-report/scripts/epidemic_report_tool.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/paper2workspace-orchestrator/scripts/workspace_tool.py"),
    ]

    for script in scripts:
        assert script.exists()
