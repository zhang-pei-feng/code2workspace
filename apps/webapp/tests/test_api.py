from pathlib import Path

from starlette.testclient import TestClient

from apps.webapp import api
from apps.webapp.store import AppStore


def test_session_lifecycle(tmp_path: Path) -> None:
    api.STORE = AppStore(tmp_path / "webapp.db")
    client = TestClient(api.app)

    created = client.post("/api/sessions", json={})
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()["sessions"][0]["id"] == session_id

    loaded = client.get(f"/api/sessions/{session_id}")
    assert loaded.status_code == 200
    assert loaded.json()["session"]["id"] == session_id

    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/api/sessions/{session_id}")
    assert missing.status_code == 404


def test_get_run_endpoint(tmp_path: Path) -> None:
    api.STORE = AppStore(tmp_path / "webapp.db")
    session = api.STORE.create_session("Run Session")
    run = api.STORE.create_run(session.id, "echo hello")
    api.STORE.complete_run(run.id, status="succeeded", output="ok", exit_code=0)
    client = TestClient(api.app)

    loaded = client.get(f"/api/runs/{run.id}")

    assert loaded.status_code == 200
    assert loaded.json()["run"]["id"] == run.id
    assert loaded.json()["run"]["status"] == "succeeded"


def test_session_subpage_serves_frontend(tmp_path: Path) -> None:
    api.STORE = AppStore(tmp_path / "webapp.db")
    session = api.STORE.create_session("Deep Link Session")
    client = TestClient(api.app)

    loaded = client.get(f"/sessions/{session.id}")

    assert loaded.status_code == 200
    assert "Code2Workspace Lab" in loaded.text


def test_static_index_references_existing_bundles() -> None:
    static_dir = Path(api.STATIC_DIR)
    index_text = static_dir.joinpath("index.html").read_text(encoding="utf-8")

    assert "/static/assets/" in index_text
    asset_dir = static_dir / "assets"
    assert asset_dir.exists()
    assert any(asset_dir.iterdir())
