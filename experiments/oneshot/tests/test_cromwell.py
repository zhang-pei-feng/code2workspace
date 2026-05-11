from pathlib import Path

from experiments.oneshot import cromwell


def test_resolve_cromwell_jar_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("CROMWELL_JAR", "custom/cromwell.jar")

    resolved = cromwell.resolve_cromwell_jar()

    assert resolved == (cromwell.repo_root() / "custom" / "cromwell.jar").resolve()


def test_build_cromwell_run_command_uses_resolved_path(monkeypatch, tmp_path: Path) -> None:
    jar_path = tmp_path / "tools" / "cromwell.jar"
    monkeypatch.setenv("CROMWELL_JAR", str(jar_path))
    wdl_path = tmp_path / "demo.wdl"
    inputs_path = tmp_path / "inputs.json"
    options_path = tmp_path / "options.json"

    cmd = cromwell.build_cromwell_run_command(
        wdl_path,
        inputs_path=inputs_path,
        options_path=options_path,
    )

    assert cmd == [
        "java",
        "-jar",
        str(jar_path),
        "run",
        str(wdl_path),
        "-i",
        str(inputs_path),
        "-o",
        str(options_path),
    ]
