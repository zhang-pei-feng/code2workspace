# code2workspace

`code2workspace` is the trimmed core of `deepagents`, repurposed as the base repository for a graduation project about turning GitHub repositories into runnable workspaces.

This repository currently keeps the parts that matter for that direction:

- `libs/deepagents`: the core agent runtime
- `libs/cli`: the terminal interface and non-interactive task runner

The original example projects, release automation, ACP package, evals package, REPL package, and partner integration packages have been removed from this repo snapshot so the codebase stays small enough to evolve into a focused research project.

## Current status

- Base runtime preserved from `deepagents`
- MCP startup fixes from local development are included
- CLI and non-interactive task execution remain usable
- Repository intentionally reduced to core modules only

## Local run

From the repository root:

```bash
uv run --project libs/cli deepagents
```

Or run a single task:

```bash
uv run --project libs/cli deepagents -n "Reply with OK only." -q
```

## Near-term direction

The next stage of this repository is to implement the `code2workspace` pipeline itself: ingest a target GitHub repository, detect its runnable surface, prepare workspace artifacts, and execute validation tasks in a reproducible way.
