# code2workspace

`code2workspace` is the implementation base for a graduation project about
agent orchestration with LangGraph and LangChain. This branch packages the
current supervisor-first agent as a portable question-answering build.

The repository root is now intentionally minimal. Most project documentation
lives under `docs/`.

## What Is Here

- `libs/code2workspace`
  - core runtime and middleware stack
- `libs/cli`
  - terminal interface and non-interactive runner
- `apps/webapp`
  - historical web workbench code; not required for the QA-only build
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

- Non-interactive QA execution is the primary path on this branch.
- Main model/runtime configuration has one project-local entrypoint:
  `backend/config/agent_models.json`.
- `.env` files and user-level `~/.code2workspace/config.toml` are not used for
  the main agent model configuration in this build.
- Supervisor Graph remains enabled, but `runtime.mode = "qa"` forces prompts
  through the generic question-answering graph instead of the old
  `github2workspace`, `benchmark`, or `report` task lanes.
- The interactive TUI startup path is working again after the deferred-startup
  message-routing hotfix.
- Normal CLI sessions now inherit the launch directory by default instead of
  creating `workspace/<YYYYMMDDHHMMSS>`.
- Experiment runners that require a fixed repo root, such as
  `experiments/oneshot` and `experiments/skill_tests`, explicitly preserve
  their original working directories instead of using the new per-session
  workspace behavior.
- Web frontend/backend and remote sandbox paths are not part of the QA-only
  runtime path.
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
  - per-session CLI working directories under the project root
- `tmp/`
  - disposable local scratch outputs and one-off probes

Keep new local run artifacts inside those existing directories rather than
creating additional root-level output folders.

## Local Run

From the repository root:

First edit `backend/config/agent_models.json` and fill
`providers.main.api_key` if your OpenAI-compatible gateway requires a key.

```bash
uv run --project libs/cli code2workspace
```

Single non-interactive task:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q
```

## Near-Term Direction

The current sequence is:

1. keep hardening the generic one-shot experiment path
2. use those runs to drive repeatable harness optimization
3. keep the remaining web API backend minimal unless a new frontend is
   intentionally introduced
4. feed the resulting evidence into the thesis narrative and future
   `code2workspace` pipeline work
