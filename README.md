# code2workspace

`code2workspace` is the implementation base for a graduation project about
turning GitHub repositories into runnable workspaces with an agent built on
LangGraph and LangChain.

The repository root is now intentionally minimal. Most project documentation
lives under `docs/`.

## What Is Here

- `libs/code2workspace`
  - core runtime and middleware stack
- `libs/cli`
  - terminal interface and non-interactive runner
- `apps/webapp`
  - minimal web control plane
- `experiments/oneshot`
  - generic one-shot repo-task runner
- `experiments/harness`
  - harness experiments and thesis-facing methodology material

## Start Reading Here

- `docs/overview/current-status.md`
  - current engineering status and blockers
- `docs/overview/roadmap.md`
  - active implementation targets
- `docs/overview/session-handoff.md`
  - shortest restart note for a new session
- `docs/research/README.md`
  - thesis and experiment-writing index
- `docs/README.md`
  - full documentation map

## Current Progress

- Non-interactive CLI execution is usable with the current local gateway setup.
- The interactive TUI is currently not in a healthy usable state and needs a
  dedicated follow-up repair pass.
- The web control plane is stable enough for session management, run
  inspection, and one-shot task submission.
- The one-shot runner has already produced real Docker/WDL success evidence on
  `spades` and `v-pipe`, with additional positive evidence on
  `covid-19-signal` and `fieldbioinformatics`.
- The harness layer now exists as a real optimization loop rather than a
  placeholder directory.

## Local Run

From the repository root:

```bash
uv run --project libs/cli code2workspace
```

Single non-interactive task:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q
```

Run the minimal web workspace:

```bash
uv run --project libs/cli python -m uvicorn apps.webapp.api:app --app-dir . --reload
```

## Near-Term Direction

The current sequence is:

1. keep the web control plane stable
2. keep hardening the generic one-shot experiment path
3. use those runs to drive repeatable harness optimization
4. feed the resulting evidence into the thesis narrative and future
   `code2workspace` pipeline work
