from pathlib import Path

from apps.webapp.store import AppStore


def test_create_and_read_session(tmp_path: Path) -> None:
    store = AppStore(tmp_path / "webapp.db")
    session = store.create_session("Test Session")
    store.append_message(session.id, role="user", content="hello")
    payload = store.get_session(session.id)

    assert payload is not None
    assert payload["session"]["title"] == "Test Session"
    assert payload["messages"][0]["content"] == "hello"


def test_maybe_update_title_from_prompt(tmp_path: Path) -> None:
    store = AppStore(tmp_path / "webapp.db")
    session = store.create_session()
    store.maybe_update_title_from_prompt(session.id, "Investigate repo task status")
    payload = store.get_session(session.id)

    assert payload is not None
    assert payload["session"]["title"].startswith("Investigate repo task status")


def test_list_sessions_includes_run_metadata(tmp_path: Path) -> None:
    store = AppStore(tmp_path / "webapp.db")
    session = store.create_session("Tracked Session")
    run = store.create_run(session.id, "echo hello")
    store.mark_run_running(run.id)
    store.complete_run(run.id, status="succeeded", output="ok", exit_code=0)

    listed = store.list_sessions()

    assert listed[0].latest_run_id == run.id
    assert listed[0].latest_run_status == "succeeded"
    assert listed[0].run_count == 1


def test_get_run_returns_persisted_run(tmp_path: Path) -> None:
    store = AppStore(tmp_path / "webapp.db")
    session = store.create_session("Run Session")
    run = store.create_run(session.id, "echo hello")
    store.complete_run(run.id, status="failed", output="boom", exit_code=1, error="boom")

    loaded = store.get_run(run.id)

    assert loaded is not None
    assert loaded["status"] == "failed"
    assert loaded["output"] == "boom"


def test_append_run_output_persists_streamed_chunks(tmp_path: Path) -> None:
    store = AppStore(tmp_path / "webapp.db")
    session = store.create_session("Stream Session")
    run = store.create_run(session.id, "echo hello")

    store.append_run_output(run.id, "first line\n")
    store.append_run_output(run.id, "second line\n")

    loaded = store.get_run(run.id)

    assert loaded is not None
    assert loaded["output"] == "first line\nsecond line\n"
