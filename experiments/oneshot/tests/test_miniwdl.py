from pathlib import Path

from experiments.oneshot import miniwdl


def test_resolve_miniwdl_cfg_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("MINIWDL_CFG", "custom/miniwdl.cfg")

    resolved = miniwdl.resolve_miniwdl_cfg()

    assert resolved == (miniwdl.repo_root() / "custom" / "miniwdl.cfg").resolve()


def test_build_miniwdl_run_command_uses_project_defaults(monkeypatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "config" / "miniwdl.cfg"
    monkeypatch.setenv("MINIWDL_CFG", str(cfg_path))
    wdl_path = tmp_path / "demo.wdl"
    inputs_path = tmp_path / "inputs.json"
    output_path = tmp_path / "outputs.json"

    cmd = miniwdl.build_miniwdl_run_command(
        wdl_path,
        inputs_path=inputs_path,
        output_path=output_path,
    )

    assert cmd == [
        "miniwdl",
        "run",
        "--cfg",
        str(cfg_path),
        "--as-me",
        str(wdl_path),
        "-i",
        str(inputs_path),
        "-o",
        str(output_path),
    ]
