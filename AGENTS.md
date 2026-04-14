# Development guidelines for code2workspace

`code2workspace` is a reduced fork of `deepagents`, kept intentionally small as the implementation base for a graduation project about converting GitHub repositories into runnable workspaces.

## Repository structure

```txt
code2workspace/
├── libs/
│   ├── deepagents/  # SDK runtime
│   └── cli/         # terminal UI and non-interactive runner
└── README.md
```

## Working rules

- Keep changes focused on `libs/deepagents` and `libs/cli`.
- Preserve current CLI and non-interactive behavior unless the task explicitly changes it.
- Prefer small, testable changes over broad refactors.
- Add or update tests when changing behavior.
- Avoid re-introducing removed modules such as examples, ACP, evals, REPL, or partner packages unless the project plan explicitly requires them.

## Useful commands

```bash
uv run --project libs/cli deepagents
uv run --project libs/cli deepagents -n "Reply with OK only." -q
uv run --project libs/cli --group test pytest
```
