# EpiMindAgent CLI

This package provides the terminal interface for `EpiMindAgent`.

It supports:

- interactive terminal usage
- non-interactive single-task execution
- MCP tool loading
- skills, threads, and agent management
- local or sandbox-backed execution flows

Run locally from the repository root:

```bash
uv run --project libs/cli EpiMindAgent
```

Single-task mode:

```bash
uv run --project libs/cli EpiMindAgent -n "Reply with OK only." -q
```
