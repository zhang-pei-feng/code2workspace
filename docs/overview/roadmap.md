# Roadmap

This file defines the current implementation target for the repository.

## Goal 1: Minimal Web API Backend

Keep the lightweight `apps/webapp` API backend minimal and reusable after the
checked-in browser frontend was removed.

### Current scope

- session list
- create session
- select session
- delete session
- submit one-shot task
- poll run status and show terminal output
- show persisted user and assistant messages
- inspect historical runs

### Explicit non-goals

- rebuilding a browser frontend right now
- full multi-turn collaborative chat UX
- auth and multi-user isolation
- MCP management UI
- rich artifact browsing

### Direction

- backend: lightweight ASGI app in this repo
- execution: reuse the existing non-interactive `code2workspace` path
- frontend: intentionally absent for now
- state: pragmatic lightweight web store for now

## Goal 2: One-Shot Repo Task Experiments

Build a generic runner for Docker + WDL tasks where the only required input is a
GitHub repository URL.

### Expected shape

- clone target repository
- derive a standardized one-shot task prompt
- run `code2workspace` once
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
3. Keep the web API backend minimal
4. Iterative refinement using real repo tasks

## Phased Plan

### Phase A: Keep The Web API Thin And Honest

Objective:
keep the remaining web layer simple after frontend removal, without letting it
become a second runtime or an undocumented side path.

Planned work:

- keep the API contract small and documented
- preserve one-shot submission and run lookup
- avoid rebuilding frontend concerns into backend routes

Acceptance:

- the API can create, inspect, and delete sessions and runs
- no checked-in browser frontend is assumed by the backend

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
- the remaining web API backend still has its own session store instead of
  sharing the CLI/TUI source of truth
- the target bioinformatics repositories are too expensive to brute-force early
- tracked `.env` is useful for local progress but unsuitable for publication

## Immediate Next Queue

1. Continue hardening the one-shot batch and heavy-repo execution path.
2. Resume or complete the remaining repository baselines after `canu` and
   `megahit`.
3. Spend more effort on harness iteration than on raw baseline accumulation.
4. Keep the remaining web API backend minimal unless a new frontend is
   intentionally reintroduced.
