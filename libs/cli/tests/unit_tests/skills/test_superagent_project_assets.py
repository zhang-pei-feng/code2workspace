"""Smoke tests for the project-level superagent skills added to code2workspace."""

from pathlib import Path

from code2workspace.backends.filesystem import FilesystemBackend
from code2workspace.middleware.skills import SkillsMiddleware
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
        "planning-guide",
        "respiratory-disease-data-fetcher",
        "respiratory-disease-wide-monitor",
        "virus-variation-query",
    }:
        assert name in by_name
        assert by_name[name]["source"] == "project"
        assert Path(by_name[name]["path"]).exists()
    assert "planning-orchestrator" not in by_name


def test_planning_guide_assets_present_and_soft_routing_only() -> None:
    skill_root = Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/planning-guide")
    skill_md = skill_root / "SKILL.md"
    source_selection = skill_root / "references" / "source-selection.md"
    checklist = skill_root / "references" / "checklist.md"
    case_index = skill_root / "references" / "case-index.md"
    local_db_case = skill_root / "references" / "case-local-database-query.md"
    monitoring_case = skill_root / "references" / "case-official-monitoring-window.md"
    literature_case = skill_root / "references" / "case-latest-literature-search.md"
    synthesis_case = skill_root / "references" / "case-cross-source-synthesis.md"
    openai_yaml = skill_root / "agents" / "openai.yaml"

    for path in (
        skill_md,
        source_selection,
        checklist,
        case_index,
        local_db_case,
        monitoring_case,
        literature_case,
        synthesis_case,
        openai_yaml,
    ):
        assert path.exists(), f"Missing planning-guide asset: {path}"

    content = skill_md.read_text(encoding="utf-8")
    assert "name: planning-guide" in content
    assert "does not force downstream execution" in content
    assert "references/source-selection.md" in content
    assert "references/checklist.md" in content
    assert "references/case-index.md" in content

    case_index_content = case_index.read_text(encoding="utf-8")
    assert "规划样板" in case_index_content
    assert "不是执行测例" in case_index_content
    assert "本地数据库检索型" in case_index_content
    assert "官方监测时效型" in case_index_content
    assert "最新论文检索型" in case_index_content
    assert "跨源综合研判型" in case_index_content

    ui_metadata = openai_yaml.read_text(encoding="utf-8")
    assert "Planning Guide" in ui_metadata
    assert "planning aid" in ui_metadata.casefold()


def test_planning_guide_metadata_loads_through_skills_middleware() -> None:
    project_root = Path("/mnt/data1/zhangpf/code2workspace")
    project_skills_dir = project_root / ".code2workspace" / "skills"
    backend = FilesystemBackend(root_dir=str(project_root), virtual_mode=False)
    middleware = SkillsMiddleware(
        backend=backend,
        sources=[str(project_skills_dir)],
    )

    result = middleware.before_agent({}, None, {})  # type: ignore[arg-type]

    assert result is not None
    metadata_by_name = {skill["name"]: skill for skill in result["skills_metadata"]}
    assert "planning-guide" in metadata_by_name
    assert metadata_by_name["planning-guide"]["path"].endswith(
        ".code2workspace/skills/planning-guide/SKILL.md"
    )


def test_shared_helper_directory_is_not_discoverable_as_skill() -> None:
    project_skills_dir = Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills")

    skills = list_skills(project_skills_dir=project_skills_dir)
    skill_names = {skill["name"] for skill in skills}

    assert "_shared-superagent-helpers" not in skill_names


def test_superagent_scripts_expose_help() -> None:
    scripts = [
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/data-governance-ops/scripts/governance_ops.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/deep-research-report/scripts/report_tool.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/epidemic-warning-report/scripts/epidemic_report_tool.py"),
        Path("/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/paper2workspace-orchestrator/scripts/workspace_tool.py"),
    ]

    for script in scripts:
        assert script.exists()


def test_workflow_skills_are_local_only_after_bioos_removal() -> None:
    benchmark_skill = Path(
        "/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/benchmark-workflow-orchestrator/SKILL.md"
    ).read_text(encoding="utf-8")
    benchmark_ui = Path(
        "/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/benchmark-workflow-orchestrator/agents/openai.yaml"
    ).read_text(encoding="utf-8")
    paper2workspace_skill = Path(
        "/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/paper2workspace-orchestrator/SKILL.md"
    ).read_text(encoding="utf-8")
    paper2workspace_ui = Path(
        "/mnt/data1/zhangpf/code2workspace/.code2workspace/skills/paper2workspace-orchestrator/agents/openai.yaml"
    ).read_text(encoding="utf-8")

    assert "Bio-OS" not in benchmark_skill
    assert "bioos-operator" not in benchmark_skill
    assert "bioos_ops.py" not in benchmark_skill
    assert "Bio-OS" not in benchmark_ui
    assert "bioos-operator" not in benchmark_ui
    assert "Bio-OS" not in paper2workspace_skill
    assert "Bio-OS" not in paper2workspace_ui
