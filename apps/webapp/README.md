# Web API Backend

`apps/webapp` now contains only the lightweight API/backend pieces that were
used by the removed web frontend.

## Current scope

- health check endpoint
- session list / create / delete
- one-shot run creation
- run lookup
- SQLite-backed persistence for sessions, messages, and runs
- background delegation to the existing non-interactive `code2workspace` CLI

## Current state

- The browser frontend and static SPA assets have been intentionally removed.
- `apps/webapp/api.py` now exposes only `/api/*` routes.
- There is no checked-in web UI under `apps/webapp/` anymore.

## Run locally

```bash
cd /mnt/data1/zhangpf/code2workspace
uv run --project libs/cli python -m uvicorn apps.webapp.api:app --app-dir . --reload
```

Then use the API directly, for example:

```bash
curl http://127.0.0.1:8000/api/health
```

## Current limitations

- sessions are still stored separately from CLI/TUI thread metadata
- execution is currently one-shot only
- no auth or multi-user isolation
- this backend remains a thin wrapper around the CLI path, not a second runtime
