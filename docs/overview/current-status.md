# Current Status

This is the fastest engineering snapshot for the repository.

## Snapshot

- Last consolidated update: 2026-04-22
- Repository scope: focused on `libs/code2workspace`, `libs/cli`, the web
  API backend, one-shot repo experiments, and harness work
- Current verified baseline: non-interactive CLI works, interactive TUI startup
  reaches a usable prompt again, the web API backend works, and the `spades`
  Docker + WDL path has reached a real successful baseline
- Additional checked-in evidence: historical one-shot completions still exist
  for `v-pipe`, `covid-19-signal`, and `fieldbioinformatics`, while the latest
  reduced evaluation adds fresh completed samples on `spades` and `megahit`
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
  - local benchmark datasets, seven checked-in case dirs, and reused `v-pipe`
    evidence for the eight-tool covid-assembly benchmark snapshot
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
- Historical one-shot end-to-end completion evidence exists for `v-pipe`,
  `covid-19-signal`, and `fieldbioinformatics`, but newer benchmark / reduced
  eval lanes now mainly use them as blocker or long-runtime controls.
- `canu` still mainly spends the budget inside first-build dependency
  convergence, while `megahit` now also has a later reduced-eval direct-retry
  completed sample.
- A thesis-ready historical one-shot summary bundle now exists under
  `results/oneshot-baseline-summary-20260422/`, so table 5-2 no longer depends
  on manual extraction from scattered raw run directories; its `rows.csv` also
  carries `completion_level` and `failure_category` for figure 5-1 / 5-2.
- A figure-ready plotting bundle now also exists under
  `results/thesis-plot-data-20260422/`, providing direct count CSVs for figure
  5-1, figure 5-2, and now figure 5-3.
- The thesis-facing asset-note bundle under
  `results/thesis-asset-notes-20260422/` now covers nine ready assets:
  table 5-2, figure 5-1, figure 5-2, table 5-3, figure 5-3, table 5-7,
  table 5-8, table 5-9, and table 5-10; table 5-7 is now framed as an
  evidence-backed soft-routing observability table rather than a fabricated
  historical router comparison.
- A thesis-ready table-data bundle now also exists under
  `results/thesis-table-data-20260422/`, providing direct CSVs for table 5-2,
  table 5-3, table 5-7, table 5-8, table 5-9, and table 5-10 so the final
  school-format manuscript no longer depends on manual table transcription
  from summaries.
- The thesis main draft now also grounds its related-work section against
  recent software-engineering agent papers rather than only generic agent
  categories:
  `SWE-agent`, `AutoCodeRover`, `Agentless`, `OpenHands`,
  `Multi-SWE-bench`, `Saving SWE-Bench`, and `SWE-EVO` are now explicitly
  contrasted with the repository-to-workspace / harness-focused line in
  chapter 1 and chapter 2.
- A single regeneration entrypoint now exists at
  `experiments/harness/regenerate_thesis_assets.py`, which reruns all current
  thesis-facing summary / plot / note generators in one command.
- A real `SWE-bench Lite` pilot line now also exists:
  - latest selected run roots in the aggregated summary:
    `results/swebench-lite-pilot/runs/20260422T212019Z`,
    `results/swebench-lite-pilot/runs/20260422T214632Z`,
    `results/swebench-lite-pilot/runs/20260423T025929Z`,
    `results/swebench-lite-pilot/runs/20260423T030947Z`,
    `results/swebench-lite-pilot/runs/20260423T033502Z`
  - summary bundle:
    `results/swebench-lite-summary-20260423/`
  - current evidence:
    five real `dev`-split pilot runs now exist
    (`marshmallow-code__marshmallow-1359`,
    `pylint-dev__astroid-1268`,
    `pydicom__pydicom-1694`,
    `marshmallow-code__marshmallow-1343`,
    `sqlfluff__sqlfluff-2419`);
    4/5 runs produced real patches, 3/5 reached official harness
    `resolved=1/1`, the latest `astroid` rerun completes official evaluation as
    `unresolved=1/1`, and the latest `sqlfluff` rerun remains an agent-side
    empty-patch sample after two `InternalServerError` attempts

Focused validation previously recorded:

- `experiments/oneshot/tests`: `9 passed`

Remaining gaps:

- heavy repos still need longer build budgets, warmer layers, or better reuse
- external clone/network failures remain possible even though they are now
  serialized properly
- the current `SWE-bench Lite` line is still only a small 5-run `dev` pilot and
  should be expanded further before claiming broader generalization
- the final target-repo baseline set is not yet complete

### 3. Local Benchmark Assets

Status: an eight-tool benchmark snapshot exists, combining seven checked-in
local case directories with one reused `v-pipe` benchmark result

- The benchmark datasets and the `新冠病毒组装` workflow assets now live under
  `experiments/benchmark/`.
- The local benchmark helper now reads
  `experiments/benchmark/datasets/benchmark_catalog.json` instead of the old
  `experiments/oneshot` path; the checked-in workspace keeps seven local case
  directories, while the thesis-facing snapshot re-attaches the earlier real
  `v-pipe` benchmark result as the eighth tool.
- Fixed local `inputs.json` files now point at live repo-local data instead of
  dead historical absolute paths.
- Current 2026-04-21 benchmark run root:
  `results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark`
- Current evidence from the checked-in benchmark snapshot:
  - WDL success: `spades`, `megahit`, `trinityrnaseq`
  - repo-native success with real outputs: `canu`, `megahit`, `trinityrnaseq`
  - explicit blocker with recorded failure evidence: `v-pipe`,
    `covid-19-signal`, `fieldbioinformatics`
  - long-running execution still in progress when last recorded:
    `Flye` repo-native, `canu` WDL

Remaining gaps:

- the helper still does not natively execute WDL runs; those are currently
  recorded via case-local Cromwell status artifacts
- `covid-19-signal` currently blocks on a network-dependent `pangoLEARN`
  fetch during image build
- `v-pipe` currently blocks in the benchmark snapshot on the mismatch between
  its expected tutorial-style input tree and the shared flat FASTQ layout
- `fieldbioinformatics` currently blocks inside WDL execution even after model
  download because `artic` is not found in the runtime command environment
- the benchmark run should be resumed and summarized again after the remaining
  long-running cases settle

### 4. Harness

Status: first local optimization loop exists

- Editable surfaces exist for the one-shot prompt and completion rubric.
- The shipped harness config now also exposes three skill-contract surfaces:
  `planning_guide_skill`, `benchmark_report_policy`, and
  `paper2workspace_phase_gate`.
- Train/holdout repo splits and baseline artifact layout are versioned.
- The local harness package supports `validate`, `run-baseline`, and
  `optimize`.
- Imported OpenClaw skill content is available as reference material.
- The outer loop now supports both a local command proposer path and a native
  `[better_agent]` proposer mode.
- Harness cases and proposer workspaces now support optional `stratum`
  labels so future optimization can group failures by mode rather than only by
  repository name.
- A deterministic `stratum_surface_proposer.py` smoke path now exists for
  testing stratum-driven surface edits without requiring a model-backed outer
  proposer.
- A checked-in smoke optimize run now exists under
  `results/harness-smoke/stratum-surface-smoke/20260422T003336Z`, where the
  deterministic proposer accepted `iter-001` and improved combined
  `train + holdout` from `0/2` to `2/2`.
- A second lightweight smoke optimize path now exists under
  `results/harness-local-repo-smoke-fixture/runs/local-repo-stratum-smoke/20260422T020117Z`;
  unlike the fully synthetic smoke path, it materializes checked-in tiny repo
  fixtures and still exercises the real `run_repo_task()` clone/prompt/
  manifest/completion flow.
- A low-cost project-skill orchestration eval lane now exists under
  `experiments/skill_tests/` for planner / orchestrator contract checks.
- Current 2026-04-22 orchestration smoke evidence:
  - unified 4-case batch: `4 passed`
    - `results/skill-tests/project-skill-orchestration/20260422`
  - derived summary bundle:
    - `results/project-skill-summary-20260422/`
- Current 2026-04-22 two-hour repo-eval evidence:
  - clean harness baseline on `spades`: `completed`
    - `results/harness-two-hour-eval/code2workspace-two-hour-eval/20260422T033624Z/history/visible/train/baseline/results/spades/20260422T033624Z`
  - direct retry on `megahit`: `completed`
    - `results/two-hour-spotcheck5/megahit/20260422T063109Z`
  - clean harness baseline on `megahit`: `finished`
    - immediate cause: model-side `APIError`, not a repository-preparation or
      completion-judgment blocker
  - direct spotcheck on `fieldbioinformatics`: `timed_out`
    - but after real image build plus real container validation attempts that
      reproduced the `artic` PATH/runtime blocker
  - direct spotcheck on `v-pipe`: `timed_out`
    - but only after entering real `docker build` and Snakemake/conda
      environment creation
  - consolidated memo:
    - `experiments/harness/TWO_HOUR_EVAL_20260422_ZH.md`
  - machine-readable summary bundle:
    - `results/harness-two-hour-eval/summary-20260422/`
  - benchmark snapshot summary bundle:
    - `results/benchmark-summary-20260421/`

Focused validation currently recorded:

- `experiments/harness/tests/test_project_skill_helpers.py` and
  `experiments/harness/tests/test_code2workspace_harness.py`: `34 passed`

Remaining gaps:

- the harness needs more real optimization cycles, not just baseline structure
- current keep/discard logic is valid but still simple
- repo-budget strategy for heavy scientific repos remains the biggest practical
  limiter
- the project-skill orchestration eval lane is still smoke-scale and should be
  expanded into a stable multi-case batch with cleaner unified summaries
- the current checked-in smoke optimize path is deterministic by design; the
  next step is to run comparable iterations against real repo-url failures
  beyond local smoke repositories
- the two-hour repo-eval set still needs a clean final aggregate summary after
  the remaining long-running or interrupted cases settle

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
  - the planning contract now also carries task-specific execution constraints
    such as fresh-output requirements, no-reuse hints, shared-dataset
    preference, strict phase gates, lane dependencies, and final synthesis /
    report expectations
  - `paper2workspace-orchestrator` run scaffolding now exposes structured
    status, completion, and report entrypoints so phase-gated workspace tasks
    can be summarized before optional expansion

### 2026-04-22

- Added stable `Planner:` / `Planner Contract:` summaries to non-interactive
  CLI logs so planner recommendations are visible and testable even in quiet
  mode.
- Upgraded the checked-in harness config from a two-case demo to the live
  `train/holdout` repo split with fixed `stratum` labels.
- Added four low-cost project-skill orchestration eval cases covering:
  benchmark routing, paper2workspace routing, mixed-task lane summaries, and
  phase-gated workspace report generation.
- Recorded initial real smoke results:
  - benchmark routing: `passed`
  - paper2workspace routing: `passed`
  - mixed-task routing: `passed`
  - phase-gated report helper: `passed`
  - unified result root:
    `results/skill-tests/project-skill-orchestration/20260422`

## Read Next

- `docs/overview/roadmap.md`
- `docs/overview/session-handoff.md`
- `apps/webapp/README.md`
- `experiments/oneshot/README.md`
- `experiments/harness/README.md`
