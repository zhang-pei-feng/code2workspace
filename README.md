# code2workspace

`code2workspace` is the development repository for a graduation project about turning GitHub repositories into runnable workspaces with an agent built on LangGraph and LangChain.

This repository currently keeps two core packages:

- `libs/code2workspace`: the core runtime and middleware stack
- `libs/cli`: the terminal interface and non-interactive task runner

Current adjunct directories:

- `apps/webapp`: minimal LangGraph-backed web workspace MVP
- `experiments/oneshot`: generic one-shot repo-task runner
- `experiments/harness`: harness-practice scaffolding

For a concise handoff of the latest verified state, local setup, and recent decisions, read `DEVELOPMENT_LOG.md`.
For the active implementation target, read `PROJECT_ROADMAP.md`.
For a short resume note for new sessions, read `SESSION_BRIEF.md`.

The original example projects, release automation, ACP package, evals package, REPL package, and partner integration packages were removed so the codebase stays focused on the graduation-project direction.

## Current status

- LangGraph + LangChain based agent runtime preserved and renamed for this project
- MCP startup fixes from local development are included
- CLI and non-interactive task execution remain usable
- Repository intentionally reduced to core modules only
- A repo-tracked local OpenAI-compatible config is available for current development
- The web control plane is intentionally kept simple and stable rather than animation-heavy
- The `spades` Docker + WDL path has been driven to a real successful baseline
- Multi-repo oneshot batch execution is running, but the batch entrypoint still needs hardening against clone/setup failures

## Local run

From the repository root:

```bash
uv run --project libs/cli code2workspace
```

Or run a single task:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q
```

Run the minimal web workspace:

```bash
uv run --project libs/cli python -m uvicorn apps.webapp.api:app --app-dir . --reload
```

## Near-term direction

The next stage of this repository is to harden the generic experiment path and
then implement the `code2workspace` harness/pipeline itself: ingest a target
GitHub repository, detect its runnable surface, prepare workspace artifacts, and
execute validation tasks in a reproducible way.
