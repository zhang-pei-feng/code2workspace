# Web Workspace

This is the current web UI for `code2workspace`.

## Current scope

- list sessions
- create sessions
- select a session
- delete a session
- manually refresh session state
- submit a one-shot task
- poll run status
- view persisted user / assistant messages
- inspect run history for a session
- inspect raw terminal output for the selected run

## Frontend direction

- the original hand-written static frontend has been replaced
- the new frontend is built from an `assistant-ui`-compatible React/Vite base
- the UI is now a three-column workspace:
  - session registry
  - message / prompt workspace
  - run inspector with raw logs
- the frontend source now lives under `apps/webapp/frontend/`
- `apps/webapp/static/` is now build output only, not the place to edit source

The backend intentionally delegates execution to the existing non-interactive
`code2workspace` CLI path, so the web workspace still uses the current
LangGraph-based runtime instead of inventing a second execution engine.

## Run locally

Build the frontend:

```bash
cd apps/webapp/frontend
npm install
npm run build
```

Then start the backend:

```bash
cd /mnt/data1/zhangpf/code2workspace
uv run --project libs/cli python -m uvicorn apps.webapp.api:app --app-dir . --reload
```

For frontend-only iteration during development:

```bash
cd apps/webapp/frontend
npm run dev
```

This serves the SPA on Vite's dev port while the Python backend continues to
serve `/api/*`.

From the repository root:

Then open:

```text
http://127.0.0.1:8000
```

## Current limitations

- web sessions are stored separately from TUI thread metadata
- execution is currently one-shot only
- workspace target is the current repository root
- no auth, no multi-user isolation, no token-level streaming
- the message workspace is already structured to evolve toward richer deepagents
  state, but the current backend still exposes the older polling-based session
  and run API

## Why this shape

The current project needs a thin web interaction layer quickly. Reusing the
existing CLI execution path keeps the LangGraph stack intact while making it
possible to iterate on UX separately from the core runtime. The current visual
direction is intentionally restrained so long-running experiment monitoring is
easy to trust and scan.
