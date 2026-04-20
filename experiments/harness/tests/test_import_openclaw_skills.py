from pathlib import Path

from experiments.harness.import_openclaw_skills import import_openclaw_skills


def test_import_openclaw_skills_copies_supported_entries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "ALL_SKILLS_GUIDE.md").write_text("guide\n", encoding="utf-8")
    (source / "keep.tar.gz").write_text("ignored?\n", encoding="utf-8")
    skill_dir = source / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Demo\n", encoding="utf-8")

    dest = tmp_path / "dest"
    copied = import_openclaw_skills(source=source, dest=dest, clean=True)

    assert dest.joinpath("ALL_SKILLS_GUIDE.md").exists()
    assert dest.joinpath("demo-skill", "SKILL.md").exists()
    assert dest.joinpath("keep.tar.gz").exists()
    assert len(copied) == 3
