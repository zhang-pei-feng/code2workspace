from pathlib import Path

from code2workspace_cli.session_workspace import prepare_session_cwd


def test_prepare_session_cwd_returns_invocation_dir_in_inherit_mode(tmp_path: Path) -> None:
    resolved = prepare_session_cwd(tmp_path, mode="inherit")
    assert resolved == tmp_path.resolve()


def test_prepare_session_cwd_creates_timestamped_workspace_dir(tmp_path: Path) -> None:
    resolved = prepare_session_cwd(
        tmp_path,
        mode="isolated",
        timestamp_factory=lambda: "20260421010203",
    )

    assert resolved == (tmp_path / "workspace" / "20260421010203").resolve()
    assert resolved.is_dir()


def test_prepare_session_cwd_retries_when_timestamp_already_exists(tmp_path: Path) -> None:
    existing = tmp_path / "workspace" / "20260421010203"
    existing.mkdir(parents=True)
    timestamps = iter(["20260421010203", "20260421010204"])

    resolved = prepare_session_cwd(
        tmp_path,
        mode="isolated",
        timestamp_factory=lambda: next(timestamps),
    )

    assert resolved == (tmp_path / "workspace" / "20260421010204").resolve()
    assert resolved.is_dir()
