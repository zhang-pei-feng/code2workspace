# Project Roadmap

This file defines the current development target for the repository.

## Goal 1: Minimal Web Workspace

Build a lightweight web interface, inspired by the DeerFlow workspace style, for
the LangGraph-backed `code2workspace` runtime.

### MVP scope

- session list
- create session
- select session
- submit one-shot task
- poll run status and show terminal output
- show user/assistant messages for the session

### Explicit non-goals for MVP

- full multi-turn collaborative chat UX
- frontend-side model configuration
- per-user auth and permission systems
- MCP management UI
- rich artifact browser

### Implementation direction

- backend: lightweight ASGI app in this repo
- execution: continue using the existing `code2workspace` non-interactive LangGraph path
- frontend: static web UI with a DeerFlow-like dark workspace layout
- session state: lightweight app store for web sessions, separate from TUI concerns

## Goal 2: One-Shot Repo Task Experiments

Build a generic runner for the Docker + WDL tasks where the only required input
is a GitHub repository URL.

### Expected shape

- clone target repository
- derive task-specific prompt from the repository URL
- run `code2workspace` in one-shot mode
- capture all real terminal output into logs
- write prompt, metadata, raw output, and summary into one run directory

### Initial target repository list

- `https://github.com/ablab/spades`
- `https://github.com/marbl/canu`
- `https://github.com/voutcn/megahit`
- `https://github.com/fenderglass/Flye`
- `https://github.com/trinityrnaseq/trinityrnaseq`
- `https://github.com/cbg-ethz/v-pipe`
- `https://github.com/jaleezyy/covid-19-signal`
- `https://github.com/artic-network/fieldbioinformatics`

### Acceptance criteria for the runner

- one command can start a run from a repo URL
- all terminal output is persisted
- prompt generation is standardized
- run outputs are easy to compare across repositories

## Goal 3: Harness Practice

Create local harness experiments inspired by `deepagents/examples/better-harness`
to improve one-shot task success rate.

### First harness milestone

- define editable surfaces
- define train / holdout repo tasks
- define run artifact layout
- define baseline-vs-candidate evaluation loop

### Candidate surfaces

- one-shot task prompt template
- planner prompt
- shell / validation policy
- task decomposition instructions
- result-completion rubric

## Goal 4: Thesis Traceability

Treat repository evolution as thesis material.

### Required practice

- keep `DEVELOPMENT_LOG.md` current
- append meaningful milestones to `THESIS_LOG.md`
- preserve architectural decisions and failures, not just successes
- leave enough context that a new session can resume work quickly

## Current execution order

1. Web workspace MVP
2. One-shot runner and prompt standardization
3. Harness structure and baseline experiments
4. Iterative refinement using real repo tasks

## Detailed execution plan

### Phase A: Make the control plane actually usable

Objective:
keep the web layer simple, but make it strong enough to drive repeated one-shot experiments without falling back to the terminal for routine session management.

Planned work:

- add explicit session deletion from the frontend
- add visible run history per session, not only the latest run
- add manual refresh and clearer session/run status indicators
- keep the backend contract minimal so the frontend can remain a static app

Acceptance:

- a new session can be created, selected, refreshed, and deleted from the browser
- one session can show multiple historical runs with status, time, and exit code
- the latest run log remains readable while older runs stay accessible

### Phase B: Turn the one-shot runner into a repeatable experiment entrypoint

Objective:
make repo-task execution comparable across repositories instead of running ad hoc prompts by hand.

Planned work:

- separate prompt template data from runner orchestration
- add a batch entrypoint that can iterate over `targets.txt`
- write a per-run manifest so every run has stable machine-readable metadata
- keep all terminal output, prompt text, and result judgment in one run directory
- make repository-preparation failures survivable inside batch mode so one bad clone does not kill the queue

Acceptance:

- one repo can be run with a single command
- a batch command can schedule multiple repos with a cap such as `--limit`
- every run directory contains prompt, manifest, raw logs, and summary

### Phase C: Populate the first real harness surfaces

Objective:
stop treating harness as an empty directory and start defining the concrete editable surfaces for this repo.

Planned work:

- expose a base one-shot prompt surface
- expose a completion rubric surface
- define train / holdout repository grouping
- define a baseline artifact layout that later optimization code can reuse

Acceptance:

- harness config files can point to named surfaces instead of prose only
- train and holdout repositories are explicit and versioned in the repo
- the artifact layout is compatible with future keep / discard loops

### Phase D: Run the first expensive baseline

Objective:
use one heavy real repository to verify that the experiment layout survives real runtime cost and noisy logs.

Planned work:

- choose one initial repository, likely `spades`
- run one baseline end to end
- record where the current agent fails, stalls, or overuses tools
- feed those observations back into harness surfaces and thesis notes

Acceptance:

- at least one real baseline directory exists under `results/`
- failures are categorized, not just logged
- the thesis log can cite one concrete experiment cycle

## Current difficulties

### Gateway compatibility

- the local OpenAI-compatible gateway works for the current CLI path only after forcing `use_responses_api = false`
- this means the local development baseline is usable, but not yet representative of the ideal OpenAI Responses tool-calling path

### Session model split

- the web workspace currently keeps its own SQLite session store
- this is pragmatic for now, but it means the browser view is not yet the same source of truth as the terminal/TUI runtime

### Experiment cost

- the target bioinformatics repositories are heavy
- running all eight repos too early would create a large pile of logs before the prompt, result schema, and harness surfaces are stable

### Publication hygiene

- `.env` is intentionally tracked for local progress right now
- this is incompatible with eventual public release and must be cleaned before publication

## Immediate next queue

1. harden the one-shot batch runner against clone/setup failures
2. resume the remaining repository baselines after `canu` and `megahit`
3. switch from baseline collection into harness implementation
4. keep the web workspace simple and stable while it serves as the experiment control plane
