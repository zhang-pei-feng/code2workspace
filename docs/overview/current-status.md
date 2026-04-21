# Current Status

This is the fastest engineering snapshot for the repository.

## Snapshot

- Last consolidated update: 2026-04-21
- Repository scope: focused on `libs/code2workspace`, `libs/cli`, the web
  API backend, one-shot repo experiments, and harness work
- Current verified baseline: non-interactive CLI works, interactive TUI startup
  reaches a usable prompt again, the web API backend works, and the `spades`
  Docker + WDL path has reached a real successful baseline
- Additional positive baseline: `v-pipe` now also completes end to end with
  matching direct-container and WDL output evidence
- Local model setup: OpenAI-compatible gateway on `http://8.221.123.105:8080/v1`
  with `use_responses_api = false`

## Repository Shape

- `libs/code2workspace`
  - core runtime, middleware, backends, and agent graph
- `libs/cli`
  - terminal UI, non-interactive runner, model/config handling, and server
    bridge
- `apps/webapp`
  - lightweight web API backend backed by the existing CLI execution path
- `experiments/oneshot`
  - generic one-shot runner for repo-to-Docker/WDL tasks
- `experiments/benchmark`
  - local benchmark datasets, fixed workflow assets, and reused seven-case
    covid-assembly benchmark area
- `experiments/harness`
  - harness optimization loop, editable surfaces, and thesis-writing material

## Workstream Progress

### 1. Web API Backend

Status: minimal backend only

- Session list, create, delete, run submission, run lookup, and health routes
  are still in place under `/api/*`.
- The checked-in browser frontend and static SPA assets have been removed.
- The web SQLite store now enables `WAL` mode plus a busy timeout so one-shot
  completion is not starved by repeated status polling.
- The backend still intentionally delegates execution to the non-interactive
  CLI path instead of introducing a second runtime.
- Focused validation currently recorded:
  - `apps/webapp/tests`: `10 passed`

Remaining gaps:

- web sessions still use a lightweight app store instead of the CLI/TUI thread
  model
- execution is still one-shot only
- there is no checked-in browser UI anymore

### 2. One-Shot Repo Runner

Status: real experiment path exists and has produced both success and failure
evidence

- Single-repo and batch entrypoints are in place.
- Each run persists `prompt.txt`, `manifest.json`, `agent.log`, and
  `summary.json`.
- Shell execution is explicitly enabled, which was necessary for honest
  Docker/WDL task execution.
- Clone/setup failures are now recorded as explicit outcomes instead of killing
  the entire batch silently.
- `spades` is the reference heavy success case.
- `v-pipe`, `covid-19-signal`, and `fieldbioinformatics` are the best current
  automatic end-to-end completion evidence.
- `canu` and `megahit` reach real Docker build execution but currently spend the
  budget inside first-build dependency convergence.

Focused validation previously recorded:

- `experiments/oneshot/tests`: `9 passed`

Remaining gaps:

- heavy repos still need longer build budgets, warmer layers, or better reuse
- external clone/network failures remain possible even though they are now
  serialized properly
- the final target-repo baseline set is not yet complete

### 3. Local Benchmark Assets

Status: seven-case local benchmark path exists and has partial real results

- The benchmark datasets and the `新冠病毒组装` workflow assets now live under
  `experiments/benchmark/`.
- The local benchmark helper now reads
  `experiments/benchmark/datasets/benchmark_catalog.json` instead of the old
  `experiments/oneshot` path, and the catalog is normalized to the seven local
  cases rather than the earlier eight-case draft.
- Fixed local `inputs.json` files now point at live repo-local data instead of
  dead historical absolute paths.
- Current 2026-04-21 benchmark run root:
  `results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark`
- Current evidence from that run:
  - WDL success: `spades`, `megahit`, `trinityrnaseq`
  - repo-native success with real outputs: `canu`, `megahit`, `trinityrnaseq`
  - explicit blocker with recorded failure evidence: `covid-19-signal`,
    `fieldbioinformatics`
  - long-running execution still in progress when last recorded:
    `Flye` repo-native, `canu` WDL

Remaining gaps:

- the helper still does not natively execute WDL runs; those are currently
  recorded via case-local Cromwell status artifacts
- `covid-19-signal` currently blocks on a network-dependent `pangoLEARN`
  fetch during image build
- `fieldbioinformatics` currently blocks inside WDL execution even after model
  download because `artic` is not found in the runtime command environment
- the benchmark run should be resumed and summarized again after the remaining
  long-running cases settle

### 4. Harness

Status: first local optimization loop exists

- Editable surfaces exist for the one-shot prompt and completion rubric.
- Train/holdout repo splits and baseline artifact layout are versioned.
- The local harness package supports `validate`, `run-baseline`, and
  `optimize`.
- Imported OpenClaw skill content is available as reference material.
- The outer loop now supports both a local command proposer path and a native
  `[better_agent]` proposer mode.

Focused validation previously recorded:

- `experiments/harness/tests`: `4 passed`

Remaining gaps:

- the harness needs more real optimization cycles, not just baseline structure
- current keep/discard logic is valid but still simple
- repo-budget strategy for heavy scientific repos remains the biggest practical
  limiter

### 5. Runtime And Local Environment

Status: locally usable with a known compatibility workaround

- Verified command:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q --no-mcp
```

- Expected result: `OK`
- The interactive TUI startup path now reaches the normal ready prompt again
  after the deferred-startup message-routing hotfix in
  `libs/cli/code2workspace_cli/app.py`.
- Normal CLI sessions now create a per-session working directory under
  `<invocation-cwd>/workspace/<YYYYMMDDHHMMSS>` and record that path in thread
  metadata so resumed threads can return to the same workspace.
- Experiment runners with fixed repo-layout assumptions currently opt out and
  keep their original working directories, notably `experiments/oneshot` and
  `experiments/skill_tests`.
- Repo-tracked config lives at `.code2workspace/config.toml`.
- Repo-tracked `.env` is intentionally committed for now during local
  development.
- The local gateway responds through chat-completions compatibility, but the
  full agent path still is not confirmed for the ideal Responses API mode.

Remaining gaps:

- decide whether tracked `.env` should become `.env.example` before publication
- revisit `use_responses_api = true` only if the local gateway later supports
  the full tool-calling flow cleanly

## Main Blockers

- heavy scientific repositories are expensive and slow to converge on cold
  Docker layers
- the remaining web API state and CLI/TUI runtime state are still split
- gateway compatibility with the ideal Responses API path is incomplete
- the inherited runtime is usable, but the repo-specific `code2workspace`
  pipeline still needs more implementation depth

## Current Priority Order

1. Continue hardening and running the generic one-shot experiment path.
2. Turn the prompt/policy surfaces into repeatable harness experiments.
3. Keep the remaining web API backend minimal.
4. Use the resulting evidence to support the thesis narrative and future
   pipeline work.

## Recent Milestones

### 2026-04-16

- Verified local CLI execution against the current OpenAI-compatible gateway.
- Added the first web workspace MVP, one-shot experiment scaffold, and harness
  skeleton.
- Converted `spades` from a pure failure case into a real Docker/WDL success
  path after fixing runner path assumptions, enabling shell tools, and refining
  the prompt surface.

### 2026-04-17

- Simplified the web UI toward a more trustworthy control-plane baseline.
- Hardened repo preparation so clone/setup failures become per-repo outcomes.
- Shifted emphasis from raw baseline collection toward actual harness
  implementation.

### 2026-04-18

- Materialized the first real harness loop with baseline/candidate variants,
  proposer workspaces, split evaluation, and keep/discard decisions.
- Upgraded one-shot completion judgment from a weak keyword check to an
  evidence-backed schema.

### 2026-04-19

- Consolidated thesis writing into outline, experiment-design, full-draft, and
  asset-matrix artifacts.
- Sharpened the heavy-repo timeout taxonomy and added stronger positive control
  evidence from `v-pipe`.

### 2026-04-21

- Restored the basic interactive TUI startup path by fixing stale Textual
  message handler names after the app-class rename to `Code2WorkspaceApp`.
- Added regression coverage for both direct handler calls and real
  `post_message(...)` dispatch of deferred startup events.
- Changed normal CLI session startup so new sessions default to
  `workspace/<timestamp>` below the invocation directory, while fixed-layout
  experiment runners explicitly preserve their original cwd.
- Fixed a web-store concurrency issue by enabling SQLite `WAL` mode and busy
  timeout handling so repeated status polling no longer leaves quick one-shot
  runs stranded in `running`.
- Removed the checked-in web frontend and static SPA assets entirely; `apps/webapp`
  is now API-only.
- Rebased the local benchmark helper and catalog onto `experiments/benchmark/`,
  updated the seven local covid-assembly case inputs to live paths, and started
  a real benchmark run with partial WDL-positive results for `spades`,
  `megahit`, and `trinityrnaseq`.
- Added a soft planner-routing layer for project skills:
  - `planning-guide` now emits structured soft recommendations such as
    `recommended_skill`, `selected_skill`, task type, lane hints, and fresh-run
    isolation hints for obvious benchmark / paper2workspace prompts
  - the shared CLI agent path now injects those recommendations into the
    system prompt via a planner middleware instead of forcing hard dispatch
  - isolated copies can now point back to the original project root through a
    `.code2workspace/project-root.txt` marker so project skills and agents stay
    visible without copying historical `results/`

## Read Next

- `docs/overview/roadmap.md`
- `docs/overview/session-handoff.md`
- `apps/webapp/README.md`
- `experiments/oneshot/README.md`
- `experiments/harness/README.md`
