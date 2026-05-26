# Roadmap

This file defines the current implementation target for the repository.

## Goal 1: Web Workbench Control Plane

Keep `apps/webapp` as a lightweight but usable Web Workbench: a Starlette
backend, a vendored Next.js chat frontend, a same-origin `/langgraph/*` proxy to
the shared local LangGraph server, and pragmatic `/api/*` management routes.

### Current scope

- browser chat UI backed by the local LangGraph server
- static frontend export served by the Python backend
- same-origin `/langgraph/*` proxy so the browser does not need the dynamic
  upstream port
- model and appearance settings APIs
- thread list/create/update/delete
- persisted history and run/event lookup
- workspace tree/file upload/download/delete helpers

### Explicit non-goals

- full multi-turn collaborative chat UX
- auth and multi-user isolation
- MCP management UI
- production-hardening the shared local LangGraph server

### Direction

- backend: lightweight Starlette app in this repo
- frontend: vendored `agent-chat-ui` Next.js app, with static export served by
  the backend
- execution: reuse the existing local LangGraph/CLI server bridge
- state: pragmatic lightweight web store plus checkpoint-backed thread history

## Goal 2: One-Shot Repo Task Experiments

Build a generic runner for Docker + WDL tasks where the only required input is a
GitHub repository URL.

### Expected shape

- clone target repository
- derive a standardized one-shot task prompt
- run `EpiMindAgent` once
- capture raw terminal output
- persist prompt, metadata, logs, and summary in one run directory

### Target repositories

- `https://github.com/ablab/spades`
- `https://github.com/marbl/canu`
- `https://github.com/voutcn/megahit`
- `https://github.com/fenderglass/Flye`
- `https://github.com/trinityrnaseq/trinityrnaseq`
- `https://github.com/cbg-ethz/v-pipe`
- `https://github.com/jaleezyy/covid-19-signal`
- `https://github.com/artic-network/fieldbioinformatics`

### Acceptance criteria

- one command starts a run from a repo URL
- all terminal output is persisted
- prompt generation is standardized
- run outputs are easy to compare across repositories

## Goal 3: Harness Practice

Create local harness experiments inspired by
`deepagents/examples/better-harness` to improve one-shot task success rate.

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

- keep `docs/overview/current-status.md` current
- append meaningful milestones to `docs/research/thesis-log.md`
- preserve failures and design decisions, not only successes
- leave enough context that a new session can restart quickly

## Execution Order

1. One-shot runner and prompt standardization
2. Harness structure and baseline experiments
3. Keep the Web Workbench control plane thin and honest
4. Iterative refinement using real repo tasks

## Phased Plan

### Phase A: Keep The Web Workbench Thin And Honest

Objective:
keep the web layer simple and reusable without letting it become a second
runtime or an undocumented side path.

Planned work:

- keep the `/langgraph/*` proxy and `/api/*` management contracts documented
- preserve browser chat, model settings, thread lookup, workspace file helpers,
  and run/event lookup
- keep execution delegated to the shared local LangGraph server rather than a
  separate web-only runtime

Acceptance:

- the Web Workbench can serve the built frontend, proxy LangGraph chat traffic,
  and expose settings/thread/workspace/run management routes
- the frontend and backend use the same local agent runtime path as CLI/TUI

### Phase B: Make The One-Shot Runner A Repeatable Experiment Entrypoint

Objective:
make repo-task execution comparable across repositories instead of running ad hoc
prompts by hand.

Planned work:

- separate prompt template data from runner orchestration
- support batch scheduling from `targets.txt`
- write a per-run manifest
- keep logs, prompt text, and result judgment in one run directory
- serialize repository-preparation failures as outcomes instead of batch-killing
  crashes

Acceptance:

- one repo can be run with a single command
- a batch command can schedule multiple repos with a cap such as `--limit`
- every run directory contains prompt, manifest, raw logs, and summary

### Phase C: Populate The First Real Harness Surfaces

Objective:
turn the harness from a placeholder area into a concrete optimization layer for
this repo.

Planned work:

- expose a base one-shot prompt surface
- expose a completion rubric surface
- define train / holdout repository grouping
- define a baseline artifact layout reusable by future optimization code

Acceptance:

- harness config files point to named surfaces
- train and holdout repositories are explicit and versioned
- artifact layout supports future keep/discard loops

### Phase D: Run The First Expensive Baseline

Objective:
use one heavy real repository to verify that the experiment layout survives real
runtime cost and noisy logs.

Planned work:

- choose one heavy initial repository, likely `spades`
- run one baseline end to end
- record where the agent fails, stalls, or overuses tools
- feed observations back into harness surfaces and thesis notes

Acceptance:

- at least one real baseline directory exists under `results/`
- failures are categorized, not just logged
- the thesis log can cite one concrete experiment cycle

## Current Difficulties

- the local OpenAI-compatible gateway still requires
  `use_responses_api = false` for the working baseline
- the Web Workbench still combines a lightweight web store with CLI/TUI
  checkpoint-backed thread state rather than having one perfectly unified source
  of truth
- the target bioinformatics repositories are too expensive to brute-force early
- tracked `.env` is useful for local progress but unsuitable for publication

## Immediate Next Queue

1. Continue hardening the one-shot batch and heavy-repo execution path.
2. Resume or complete the remaining repository baselines after `canu` and
   `megahit`.
3. Spend more effort on harness iteration than on raw baseline accumulation.
4. Keep the Web Workbench useful but thin; avoid turning it into a separate
   production runtime.
