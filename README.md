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
  - minimal web API backend for the removed frontend
- `experiments/oneshot`
  - generic one-shot repo-task runner
- `experiments/harness`
  - harness experiments and thesis-facing methodology material

## Start Reading Here

- `docs/overview/current-status.md`
  - current engineering status and blockers
- `docs/overview/repo-layout.md`
  - root directory policy for source, generated artifacts, and disposable cache
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
- The interactive TUI startup path is working again after the deferred-startup
  message-routing hotfix.
- Normal CLI sessions now default to a per-session working directory under
  `<invocation-cwd>/workspace/<YYYYMMDDHHMMSS>`.
- Experiment runners that require a fixed repo root, such as
  `experiments/oneshot` and `experiments/skill_tests`, explicitly preserve
  their original working directories instead of using the new per-session
  workspace behavior.
- The repository still has a small web API backend under `apps/webapp`, but the
  checked-in web frontend has been removed.
- The one-shot runner has already produced real Docker/WDL success evidence on
  `spades` and `v-pipe`, with additional positive evidence on
  `covid-19-signal` and `fieldbioinformatics`.
- The harness layer now exists as a real optimization loop rather than a
  placeholder directory.

## Generated Directories

- `results/`
  - retained experiment outputs and benchmark evidence worth comparing later
- `.workspaces/`
  - historical experiment workspaces and other large intermediate run areas
- `workspace/`
  - per-session CLI working directories under `<invocation-cwd>/workspace/<timestamp>`
- `tmp/`
  - disposable local scratch outputs and one-off probes

Keep new local run artifacts inside those existing directories rather than
creating additional root-level output folders.

## Local Run

From the repository root:

```bash
uv run --project libs/cli code2workspace
```

Single non-interactive task:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q
```

Run the web API backend:

```bash
uv run --project libs/cli python -m uvicorn apps.webapp.api:app --app-dir . --reload
```

## Near-Term Direction

The current sequence is:

1. keep hardening the generic one-shot experiment path
2. use those runs to drive repeatable harness optimization
3. keep the remaining web API backend minimal unless a new frontend is
   intentionally introduced
4. feed the resulting evidence into the thesis narrative and future
   `code2workspace` pipeline work
