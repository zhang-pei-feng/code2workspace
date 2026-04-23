# Current Status

This is the fastest engineering snapshot for the repository.

## Snapshot

- Last consolidated update: 2026-04-23
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
- Each one-shot run now clears prior generated Docker/WDL/Cromwell artifacts
  before execution, and permission-blocked old result directories are moved
  aside as `*.stale.<timestamp>` instead of aborting the run.
- Clone/setup failures are now recorded as explicit outcomes instead of killing
  the entire batch silently.
- `spades` is the reference heavy success case.
- `v-pipe`, `covid-19-signal`, and `fieldbioinformatics` are the best current
  automatic end-to-end completion evidence.
- `canu` and `megahit` reach real Docker build execution but currently spend the
  budget inside first-build dependency convergence.

Focused validation currently recorded:

- `experiments/oneshot/tests/test_tasks.py`: `14 passed`

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

Status: first local optimization loop exists, with both a phase-1 benchmark-autonomy ladder and a simple eight-repository real-task harness split

- Editable surfaces exist for the one-shot prompt and completion rubric.
- Train/holdout repo splits and baseline artifact layout are versioned.
- The local harness package supports `validate`, `run-baseline`, and
  `optimize`.
- The same harness package now also supports `validate-benchmark-autonomy` and
  `run-benchmark-autonomy` against the local `experiments/benchmark` assets.
- A new `benchmark_repo_harness.toml` config now uses the full eight-repository
  Docker+WDL task set through the existing one-shot runner, with a 5-repo
  train split and a 3-repo holdout/validation split sourced from
  `configs/repo_splits.toml`.
- The first debugging-oriented train baseline for that config exists under:
  `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T090923Z`
- That initial train baseline exposed two important evaluation/runtime issues
  before any outer optimization loop was attempted:
  - shared `.workspaces/oneshot/<repo>` history polluted fresh runs until the
    one-shot runner started clearing/quarantining prior generated artifacts
  - the completion judge undercounted real success for `Flye` because it only
    recognized `docker_run_test.log` and required a repo-root WDL even when the
    copied WDL in `results/wdl_file/` was correct
- Clean rerun baselines now exist for both splits:
  - `train`:
    `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T105103Z`
  - `holdout`:
    `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T105606Z`
- Current real baseline evidence from those reruns:
  - `train`: `3/5` completed
    - passed: `spades`, `megahit`, `trinityrnaseq`
    - failed: `canu`, `Flye`
  - `holdout`: `2/3` completed
    - passed: `covid-19-signal`, `fieldbioinformatics`
    - failed: `v-pipe`
  - combined baseline across all 8 real repos: `5/8`
- The next train rerun after the prompt-surface tightening lives under:
  `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T153031Z`
  - it stayed at `3/5`, but the miss shape changed materially:
    - passed: `spades`, `Flye`, `trinityrnaseq`
    - failed: `canu`, `megahit`
  - both remaining misses were early `RemoteException` /
    `RemoteProtocolError` internal failures rather than ordinary repo-task
    execution failures
- Current dominant remaining failure modes:
  - transient remote/internal agent failures can still kill a repo run before
    any fresh artifacts are produced
  - completion judging can still undercount real success when a repository uses
    a non-standard container execution log name such as
    `docker_canu_meryl.log`
- Two more focused fixes are now in place on top of the earlier freshness and
  `Flye`-judge fixes:
  - the one-shot runner now retries up to two times on narrow
    `Unexpected error (RemoteException)` / internal-error signatures while
    preserving prior failed attempts as `agent.retry*.log`
  - the completion judge now accepts fresh non-standard Docker execution logs
    under `results/docker_test/` instead of only the earlier hard-coded log
    names
- Live post-fix repro evidence now exists under:
  `results/oneshot-repro/`
  - `megahit` completed end to end in
    `results/oneshot-repro/megahit/20260422T201219Z`
  - `canu` completed real Docker + Cromwell execution in
    `results/oneshot-repro/canu/20260422T201219Z`; its original summary was
    undercounted only by the old docker-log-name judge gap, and now recomputes
    as a full completion under the fixed judge
- A fresh train rerun with the retry-enabled runner and the widened completion
  judge is currently in progress under:
  `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T203210Z`
  - persisted train result: `4/5`
    - passed: `spades`, `canu`, `megahit`, `Flye`
    - persisted miss: `trinityrnaseq`
  - under the current completion logic, the persisted `trinityrnaseq` miss is
    now understood as another evaluator false negative rather than a true task
    failure:
    - the run produced fresh `cromwell_run_retry2.log`,
      `metadata_retry2.json`, and real WDL output files
    - re-judging the same artifacts with the updated completion code now yields
      `completed=true`
  - the train split is therefore effectively `5/5` under current code
    semantics
- A fresh holdout rerun with the same fixes now exists under:
  `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260423T023441Z`
  - persisted holdout result: `2/3`
    - passed: `v-pipe`, `covid-19-signal`
    - failed: `fieldbioinformatics`
  - the important movement is that `v-pipe` has flipped from the earlier
    holdout miss into a full real Docker + WDL pass
- Current effective combined picture:
  - persisted totals: `6/8`
  - effective totals under the updated completion code: `7/8`
  - only remaining clear miss: `fieldbioinformatics`
- Imported OpenClaw skill content is available as reference material.
- The outer loop now supports both a local command proposer path and a native
  `[better_agent]` proposer mode.
- The first autonomy ladder is intentionally narrow and thesis-friendly:
  - phase 1 includes only `spades`, `megahit`, `canu`, and `Flye`
  - four levels separately test fixed execution, tool choice, input choice,
    and run-local WDL editing
  - isolated run staging now copies benchmark assets and datasets into a fresh
    workspace while preserving project skill visibility through
    `.code2workspace/project-root.txt`
  - current recorded outcomes: all four short-read levels completed
    successfully without WDL edits; long-read levels 1-2 completed with Canu
    success and Flye failure caused by the broken staged Flye image

Focused validation currently recorded:

- `experiments/oneshot/tests/test_tasks.py`: `18 passed`
- `experiments/harness/tests/test_code2workspace_harness.py`: `11 passed`

Remaining gaps:

- the harness needs more real optimization cycles, not just baseline structure
- current keep/discard logic is valid but still simple
- repo-budget strategy for heavy scientific repos remains the biggest practical
  limiter
- `fieldbioinformatics` is now the main remaining real-task miss; the latest
  holdout run shows it still stops before producing fresh Docker/WDL artifacts,
  so the next optimization loop should target that repository specifically
- independent repro work has already narrowed the likely repo-level cause:
  Docker and the shortest real container validation can be reached, but the
  WDL path is brittle because Cromwell launches the image with `/bin/bash`,
  bypassing environment activation and leaving `artic` unavailable on `PATH`
- the benchmark-autonomy ladder currently verifies contract/report behavior
  through focused tests, but it still needs real phase-1 matrix runs to gather
  completion/time/cost evidence
- the next practical step is to turn the remaining baseline misses (`canu`,
  `Flye`, `v-pipe`) into the first real harness optimization targets rather
  than collecting more raw baselines

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

### 6. Multi-Source Report Skill

Status: unified report entrypoint in place

- The two earlier report-generation skills, `deep-research-report` and
  `epidemic-warning-report`, have been removed and replaced by one new project
  skill: `multi-source-report`.
- The new skill combines a deep-research-style workflow with the repo's current
  local evidence sources:
  - orchestrator flow: plan -> init run dir -> parallel research lanes ->
    synthesize -> compose -> verify
  - first-class evidence skills: `academic-search`,
    `respiratory-disease-wide-monitor`,
    `respiratory-disease-data-fetcher`, `epietl-api`,
    `virus-variation-query`
- The old report-specific project subagents have also been replaced with
  generic report subagents:
  - `report-researcher`
  - `report-synthesizer`
  - `report-web-researcher`
- The report helper now writes all report runs under
  `results/skills/multi-source-report/` and keeps `manifest.json`,
  `lanes/*.md`, `final_report.md`, and `report_diagnostics.json` together.
- Formal `multi-source-report` runs now default to long-form output
  (`5000+` Chinese characters) and prefer Markdown tables when lanes provide
  trustworthy numeric evidence with explicit time and source fields.
- The report helper now accepts structured `Table Candidate:` blocks in lane
  notes and composes them into a `Key Data Tables` section when the numeric
  evidence is good enough; otherwise it writes an explicit “no reliable numeric
  table” note instead of fabricating a table.
- Planner routing now recommends `multi-source-report` for obvious formal
  report / deep-research prompts instead of leaving them on the generic path.
- Focused validation currently recorded:
  - `libs/cli/tests/unit_tests/test_superagent_project_subagents.py`
  - `libs/cli/tests/unit_tests/skills/test_superagent_project_assets.py`
  - `libs/code2workspace/tests/unit_tests/test_report_nested_subagents.py`
  - `experiments/skill_tests/tests/test_runner.py`
  - `experiments/skill_tests/tests/test_parsers.py`
  - `experiments/skill_tests/tests/test_multi_source_report_tool.py`
  - `experiments/harness/tests/test_code2workspace_harness.py`
  - combined focused result for the latest table-aware report pass: `45 passed`
- Live report-artifact checks now exist under:
  - `results/skill-tests/20260423-msr-behavior/`
  - `results/skill-tests/20260423-msr-structure/`
  - `results/skill-tests/20260423-msr-e2e/`

Remaining gaps:

- a direct non-interactive end-to-end prompt that returns the full report body
  in chat was started, but it was not cleanly verified to completion in this
  session
- the behavior case shows parallel `task()` usage, but the current runtime log
  format still does not expose the project subagent name in a way that the
  live-eval parser can recover reliably from tool traces alone
- a chart/image pipeline still does not exist; v1 formal-report enhancement is
  table-first rather than figure-first

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

### 2026-04-23

- Replaced the two earlier report skills with one new project skill,
  `multi-source-report`, and removed the old report-specific subagents in favor
  of `report-researcher`, `report-synthesizer`, and `report-web-researcher`.
- Rebased report orchestration on a deep-research-style lane workflow while
  keeping the current repo's local evidence skills as first-class sources.
- Added focused unit coverage and new live skill-test cases for
  `multi-source-report`, including a behavior case, a structure/materialization
  case, and a risk-oriented end-to-end artifact case.
- Extended `multi-source-report` again so formal reports now prefer
  source-backed Markdown tables when lanes provide valid numeric evidence, while
  still defaulting to `5000+` Chinese characters and explicitly declining to
  tabulate weak or incomplete numeric fragments.

## Read Next

- `docs/overview/roadmap.md`
- `docs/overview/session-handoff.md`
- `apps/webapp/README.md`
- `experiments/oneshot/README.md`
- `experiments/harness/README.md`
