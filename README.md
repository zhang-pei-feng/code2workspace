# code2workspace

`code2workspace` is the development repository for a graduation project about turning GitHub repositories into runnable workspaces with an agent built on LangGraph and LangChain.

This repository currently keeps two core packages:

- `libs/code2workspace`: the core runtime and middleware stack
- `libs/cli`: the terminal interface and non-interactive task runner

The original example projects, release automation, ACP package, evals package, REPL package, and partner integration packages were removed so the codebase stays focused on the graduation-project direction.

## Current status

- LangGraph + LangChain based agent runtime preserved and renamed for this project
- MCP startup fixes from local development are included
- CLI and non-interactive task execution remain usable
- Repository intentionally reduced to core modules only

## Local run

From the repository root:

```bash
uv run --project libs/cli code2workspace
```

Or run a single task:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q
```

## Near-term direction

The next stage of this repository is to implement the `code2workspace` pipeline itself: ingest a target GitHub repository, detect its runnable surface, prepare workspace artifacts, and execute validation tasks in a reproducible way.
