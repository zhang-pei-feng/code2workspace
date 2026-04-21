"""ASGI app for the minimal Code2Workspace web API."""

from __future__ import annotations

import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from apps.webapp.runner import queue_one_shot_run
from apps.webapp.store import AppStore

STORE = AppStore()


async def health(_: Request) -> JSONResponse:
    """Return a simple health payload."""
    return JSONResponse({"ok": True})


async def list_sessions(_: Request) -> JSONResponse:
    """Return all sessions."""
    payload = [session.__dict__ for session in STORE.list_sessions()]
    return JSONResponse({"sessions": payload})


async def create_session(request: Request) -> JSONResponse:
    """Create a new session."""
    raw = await request.body()
    payload = json.loads(raw) if raw else {}
    session = STORE.create_session(payload.get("title"))
    return JSONResponse({"session": session.__dict__}, status_code=201)


async def get_session(request: Request) -> JSONResponse:
    """Return one session with messages and runs."""
    session = STORE.get_session(request.path_params["session_id"])
    if session is None:
        return JSONResponse({"error": "session_not_found"}, status_code=404)
    return JSONResponse(session)


async def delete_session(request: Request) -> JSONResponse:
    """Delete one session."""
    deleted = STORE.delete_session(request.path_params["session_id"])
    if not deleted:
        return JSONResponse({"error": "session_not_found"}, status_code=404)
    return JSONResponse({"deleted": True})


async def create_run(request: Request) -> JSONResponse:
    """Queue one one-shot run for a session."""
    session_id = request.path_params["session_id"]
    session = STORE.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "session_not_found"}, status_code=404)
    payload = await request.json()
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return JSONResponse({"error": "prompt_required"}, status_code=400)
    run = queue_one_shot_run(STORE, session_id, prompt)
    return JSONResponse(run, status_code=202)


async def get_run(request: Request) -> JSONResponse:
    """Return one run."""
    run = STORE.get_run(request.path_params["run_id"])
    if run is not None:
        return JSONResponse({"run": run})
    return JSONResponse({"error": "run_not_found"}, status_code=404)


app = Starlette(
    debug=True,
    routes=[
        Route("/api/health", health),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions", create_session, methods=["POST"]),
        Route("/api/sessions/{session_id}", get_session, methods=["GET"]),
        Route("/api/sessions/{session_id}", delete_session, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/runs", create_run, methods=["POST"]),
        Route("/api/runs/{run_id}", get_run, methods=["GET"]),
    ],
)
