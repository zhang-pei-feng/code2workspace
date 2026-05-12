# Current Status

This is the fastest engineering snapshot for the repository.

## Snapshot

- Last consolidated update: 2026-05-08
- Repository scope: focused on `libs/code2workspace`, `libs/cli`, the Web
  Workbench, one-shot repo experiments, and harness work
- Current verified baseline: non-interactive CLI works, interactive TUI startup
  reaches a usable prompt again, the Web Workbench backend/frontend service
  works, the `spades`
  Docker + WDL path has reached a real successful baseline, and the
  supervisor-runtime worktree now has a generic graph skeleton that matches the
  intended `init -> parallel workers -> compose -> summarize` shape.
- Thesis draft status: the active Chinese thesis materials under
  `experiments/harness/` use the synchronized `test-agent-8081` thesis version
  as the baseline, while adding back a compact technical-principles section.
  The active draft now uses `绪论 -> 相关技术基础与系统需求分析 -> 系统总体设计
  -> 关键机制设计与实现 -> 实验结果与分析`, with section 1.4 kept in the
  paragraph-style research-problem form preferred for the formal thesis. The
  thesis-facing long-task story now treats Supervisor Graph as the final
  demonstration path, keeps one-shot as the historical baseline / launcher
  layer, intentionally does not present the `report` family in the thesis
  results or diagrams, and no longer presents the local harness loop as a thesis
  method. The formal paper framing is now Supervisor Graph orchestration,
  node-level artifacts, and evidence-backed completion judgment.
- New orchestration baseline: the CLI default runtime no longer relies only on
  soft planner routing for long tasks; it now wraps the base agent in a
  supervisor graph runtime that:
  - routes every user task through the supervisor layer first
  - uses a generic default graph for unknown tasks
  - uses known-family guidance/templates for `github2workspace`, `benchmark`,
    and `report`
  - executes those rounds through one supervisor worker runner contract, with
    non-deterministic nodes dispatched to a dedicated worker agent runnable and
    deterministic benchmark helpers kept as adapters
  - writes canonical orchestration artifacts under the current thread workspace
    at `orchestration_runs/<run_id>/`
  - rebuilds and queries a lightweight SQLite case index from workspace
    artifacts before planning each run
- Branch note: `feature/supervisor-graph-runtime` is the supervisor-first
  runtime branch before the QA-only packaging pass. It keeps the normal
  user-level model config / `.env` behavior, isolated project-root session
  workspaces, and all Supervisor Graph task families (`generic`,
  `github2workspace`, `benchmark`, and `report`).
- Current user-level default model now points at the custom alias
  `openai_paid:gpt-5.4`:
  - `openai` remains available as `OpenAI（自己的中转）`
  - `openai_paid` is the current default as `OpenAI（付费中转）`
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
  - Web Workbench: Starlette backend, vendored Next.js chat frontend, same-origin
    `/langgraph/*` proxy, `/api/*` management routes, and shared local LangGraph
    server startup
- `experiments/oneshot`
  - generic one-shot runner for repo-to-Docker/WDL tasks
- `experiments/benchmark`
  - local benchmark datasets, seven checked-in case dirs, and reused `v-pipe`
    evidence for the eight-tool covid-assembly benchmark snapshot
- `experiments/harness`
  - harness optimization loop, editable surfaces, and thesis-writing material

## Workstream Progress

### 0. Supervisor Graph Runtime

Status: v1 default wrapper is in place for `github2workspace`, `benchmark`,
`report`, and a newly hardened generic path

- Added `libs/code2workspace/code2workspace/orchestration_runtime.py` as the
  core graph planner/executor surface, with typed graph nodes/edges, worker
  results, execution rounds, case traces, supervisor decisions, a generic
  planner path, and a task-guidance registry.
- Added `libs/cli/code2workspace_cli/supervisor_runtime.py` as the CLI-facing
  runtime wrapper, artifact writer, and SQLite case-index layer.
- Added `libs/cli/code2workspace_cli/supervisor_capabilities.py` plus
  `.code2workspace/skills/orchestration/supervisor-guidance/` so node strategy now comes from
  versioned Skill assets while capability-to-tool mappings stay in code.
- Generic QA orchestration guidance is now stronger at the worker-contract
  layer:
  - capability bundles are no longer only one-line summaries; they now carry
    structured execution-focus / preferred-input / expected-output / stop /
    avoid contracts
  - generic tasks now always carry the `generic_qa` family guidance id
  - new guidance assets were added for `init_generic`, `worker_context`,
    `worker_solution`, `compose_generic`, and the `generic_qa` family
- `create_cli_agent()` now builds the original workspace agent as the base
  worker/fallback agent, then wraps it in a supervisor-enabled graph so every
  task enters supervisor first; generic tasks use the default graph, while known
  families receive guidance/template overlays.
- Supervisor worker execution now has an explicit runner boundary:
  - `SupervisorWorkerRunner` checks deterministic adapters first, then dispatches
    normal worker nodes to a dedicated worker agent runnable instead of invoking
    the base chat agent directly
  - the older `_invoke_worker_agent()` path remains as a compatibility helper
    and still shares the same worker prompt/result parser
  - subagent runnable construction was fixed so normal subagents are available
    even when no HITL `interrupt_on` config is present
- Generic graph planning has now been tightened further:
  - first-round generic graphs no longer stop at a single `analyze_task` node
  - they now default to `init_generic -> worker_context -> worker_solution ->
    compose_generic -> summarize`
  - classification fallback and LLM prompt rules now explicitly keep prompts
    such as `先给我一个口头判断` / `不要正式写作` on the generic path rather
    than drifting into the report family
- Fresh focused evidence from
  `experiments/harness/runs/supervisor-routing-trigger-eval/20260507T143455346391Z/`
  shows the generic family now reaches `5/5` correct under rules fallback, with
  all five generic prompts mapping to the new graph skeleton. That replay did
  not use the paid relay model because the current shell lacked
  `OPENAI_API_KEY`, so it should be repeated with live credentials before using
  the result as classifier-quality evidence.
- New static multi-case capability-prompt evidence under
  `experiments/harness/runs/generic-capability-prompt-eval/20260510T174323Z/`
  covers five business-task categories (`code_fix`, `data_analysis`,
  `incident_triage`, `solution_comparison`, `migration_plan`); all five kept the
  generic graph, loaded `generic_qa` family guidance, and included the richer
  capability-contract fields plus the expected node-specific hint.
- Cleaned up one more layer of obsolete architecture on the current branch:
  - removed the dead `paper2workspace` skill shell
  - removed the unused CLI `planner_routing.py` middleware/test surface
  - removed the thin `github2workspace-orchestrator` Skill wrapper now that
    `github2workspace` is represented directly by the supervisor task family
  - removed the checked-in report-only project subagents under
    `.code2workspace/agents/`
  - removed the retired harness-side `OpenClaw` / `ACPX` bridge assets under
    `experiments/harness/skills/openclaw/` plus the importer/test surfaces
  - retired the old `planning-guide` side helper from the active routing story;
    task-family classification now belongs to the shared supervisor runtime
    entry in `libs/code2workspace/code2workspace/orchestration_runtime.py`
- Task-family routing for the three special lanes now uses a hybrid classifier:
  - rule markers still provide the stable fast path and fallback
  - the shared runtime can ask the configured LLM to choose among
    `benchmark`, `github2workspace`, `report`, and `generic`
  - low-confidence or invalid classifier output falls back to the rule result
- Current artifact contract for supervised runs:
  - `request.json`
  - `retrieved_cases.json`
  - `graph_round_*.json`
  - `node_traces/*.json`
  - `worker_outputs/*.json`
  - `tool_activity.jsonl`
  - `final_decision.json`
  - `final_summary.md`

Focused validation currently recorded:

- `libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py`: `4 passed`
- `libs/cli/tests/unit_tests/test_supervisor_runtime.py`: `3 passed`
- server/runtime hardening after live benchmark stall:
  - `libs/cli/tests/unit_tests/test_server_helpers.py`
  - `libs/cli/tests/unit_tests/test_supervisor_runtime.py`
  - `23 passed`
- benchmark fan-out regression check:
  - `libs/cli/tests/unit_tests/test_supervisor_runtime.py`
  - `libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py`
  - `22 passed`
- targeted CLI/runtime regression suite:
  - `libs/cli/tests/unit_tests/test_agent.py`
  - `libs/cli/tests/unit_tests/test_non_interactive.py`
  - `libs/cli/tests/unit_tests/test_server_graph.py`
  - `libs/code2workspace/tests/unit_tests/test_graph.py`
  - `175 passed`
- TUI startup-facing unit checks:
  - `libs/cli/tests/unit_tests/test_app.py -k 'server_ready_message_dispatch_clears_connecting or initial_skill_runs_after_server_ready or deferred_actions_cleared_on_server_failure'`
  - `3 passed`
- Real non-interactive smoke with an external model provider remains
  environment-dependent:
  - one earlier explicit `openai:gpt-5.4` run exited successfully
  - the latest 30-second rerun timed out under the same external provider path,
    so treat live-provider confidence as weaker than the targeted unit suite
- New live benchmark-specific evidence:
  - the earlier helper-first smoke failed immediately with
    `RemoteException: BlockingError` until the CLI server was changed to start
    `langgraph dev` with `--allow-blocking`
  - benchmark `register`, catalog-selected per-case execution nodes, and
    `summarize` now have deterministic helper-backed execution paths inside
    `libs/cli/code2workspace_cli/supervisor_runtime.py`
  - deterministic benchmark worker execution is offloaded from the async event
    loop so ready per-tool workers can truly fan out after `register` instead
    of serializing on blocking helper subprocesses
  - fresh smoke run root:
    `workspace/20260505145718/orchestration_runs/20260505T065722Z`
    now reaches `register finished` and enters real SPAdes execution instead of
    stalling on the first node with only `node_started`
  - full parallel fan-out run root:
    `workspace/202605051600_parallel/orchestration_runs/20260505T081847Z`
    completed `register -> spades/megahit -> summarize` in one round; its
    `tool_activity.jsonl` records `spades` and `megahit` both starting before
    either branch finished, then `megahit` finishing while `spades` continued
  - the same two-tool benchmark also completed through the outer
    `code2workspace -n ... -q` path under
    `workspace/20260505165456/orchestration_runs/20260505T085500Z`, with the
    same fan-out event order and final `decision=stop`
  - a less prescriptive natural prompt that only provided the benchmark path,
    dataset (`short-read-ecoli-srr001666`), and metrics also completed under
    `workspace/20260505185712/orchestration_runs/20260505T105716Z`; the planner
    selected `spades` and `megahit` itself, then the summary path was tightened
    to emit an explicit metric comparison / overall judgment
  - the benchmark runtime/guidance coupling to specific tool names was removed:
    tool selection now comes from `experiments/benchmark/datasets/benchmark_catalog.json`,
    case expected outputs come from each case manifest, and generic
    `benchmark_case` guidance replaces tool-specific node guidance; a fresh
    natural-prompt CLI run under
    `workspace/20260505212743/orchestration_runs/20260505T132747Z` still
    completed with the same fan-out order and final comparison
  - after deleting the benchmark catalog/readmes, a long-read natural prompt
    under `workspace/20260506092525/orchestration_runs/20260506T012529193142Z`
    no longer selected tools and failed at `register` with
    `missing_selected_tools`; this confirms the current deterministic benchmark
    path still depends on an explicit tool-selection source rather than model or
    asset inspection

Remaining gaps:

- the planner is still heuristic/programmatic rather than model-generated
- known-family graph skeletons are still code-defined even though node strategy
  is now skill-backed
- worker recursion is designed into the contract and the first direct worker
  runner boundary is in place, but node-specific worker/subagent mappings are
  still coarse rather than fully specialized per capability
- the real interactive TUI startup smoke still timed out under scripted capture
  even though the focused startup unit checks passed
- the main benchmark supervisor path now has full two-tool end-to-end evidence;
  the remaining adjacent issue is CLI/client behavior when a user interrupts a
  long blocking helper run mid-stream
- catalog-free benchmark operation is not yet implemented: without
  `benchmark_catalog.json`, the supervisor currently does not let the model
  inspect benchmark assets and create the per-tool fan-out graph itself

### 1. Web Workbench

Status: browser chat workbench plus thin backend/proxy

- The checked-in browser frontend is present again under
  `apps/webapp/frontend/` as a vendored `agent-chat-ui` Next.js app.
- The Starlette backend serves `frontend/out/` for `/` and other non-API routes
  when the static export exists.
- On backend startup, `SharedLangGraphService` starts one shared local LangGraph
  server through the existing CLI server bridge.
- `/langgraph/*` is proxied to that shared server so the browser can stream chat
  traffic through the same-origin backend without knowing the dynamic upstream
  port.
- `/api/*` management routes remain for health, model/appearance settings,
  thread summaries, history, workspace file operations, run lookup, interrupts,
  and human decisions.
- The web SQLite store now enables `WAL` mode plus a busy timeout so one-shot
  completion is not starved by repeated status polling.
- The web layer still intentionally reuses the local LangGraph/CLI server bridge
  instead of introducing a second runtime.
- Focused validation currently recorded:
  - `apps/webapp/tests`: `10 passed`

Remaining gaps:

- web metadata still uses a lightweight app store alongside checkpoint-backed
  CLI/TUI thread state
- the shared local LangGraph server is local-development oriented rather than
  production hardened
- the current frontend is chat-first; the earlier custom workspace/run dashboard
  is not the active UI

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

Focused validation currently recorded:

- `experiments/oneshot/tests/test_tasks.py`: `14 passed`

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
- The benchmark dataset layer has now been widened beyond virus assembly:
  - restored a checked-in `experiments/benchmark/datasets/benchmark_catalog.json`
    after the worktree-local copy had gone missing
  - kept the currently wired virus-assembly dataset entries intact
  - added shared-dataset candidate entries for `cirrna` and `免疫逃逸`
    so those task families now have one unified dataset registry even though
    their tool-local `input.json` files still contain historical example paths
- New non-assembly dataset groups currently staged in the catalog:
  - `circrna-hela-rnaser-paired`
  - `circrna-blood-prjna722046`
  - `immune-escape-rbd-functional-dms`
  - `immune-escape-rbd-antibody-escape`
  - `immune-escape-covabdab-structural-bundle`
- Current benchmark directory now also has family-level README guides under:
  - `experiments/benchmark/README.md`
  - `experiments/benchmark/cirrna/README.md`
  - `experiments/benchmark/免疫逃逸/README.md`
  These explain an important design choice:
  - `cirrna` can honestly share RNA-seq/reference bundles across many tools
  - `免疫逃逸` is modality-heterogeneous, so the fair shared-benchmark shape is
    a two-layer bundle (`DMS` tables plus structure/sequence assets) rather
    than one fake “single input file for all tools”
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

Status: first local optimization loop exists, with both a phase-1 benchmark-autonomy ladder and a simple eight-repository real-task harness split

- Editable surfaces exist for the one-shot prompt and completion rubric.
- The shipped harness config now also exposes three skill-contract surfaces:
  `planning_guide_skill`, `benchmark_report_policy`, and
  `paper2workspace_phase_gate`.
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

- `experiments/oneshot/tests/test_tasks.py`: `20 passed`
- `experiments/harness/tests/test_code2workspace_harness.py`: `11 passed`
- targeted integrated regression set spanning oneshot, harness, skill-tests,
  and relevant CLI/report-routing paths: `142 passed`

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
- the project-skill orchestration eval lane is still smoke-scale and should be
  expanded into a stable multi-case batch with cleaner unified summaries
- the current checked-in smoke optimize path is deterministic by design; the
  next step is to run comparable iterations against real repo-url failures
  beyond local smoke repositories
- the two-hour repo-eval set still needs a clean final aggregate summary after
  the remaining long-running or interrupted cases settle

### 5. Runtime And Local Environment

Status: supervisor-runtime branch uses the normal user-level CLI configuration

- Main configuration entry:

```txt
~/.code2workspace/config.toml
```

- Project and global `.env` loading remain enabled. For the local relay, keep
  the relevant provider key in the shell or dotenv layer used by the CLI.
- Smoke command:

```bash
uv run --project libs/cli code2workspace -n "Reply with OK only." -q
```

- Expected result: `OK`
- The interactive TUI startup path now reaches the normal ready prompt again
  after the deferred-startup message-routing hotfix in
  `libs/cli/code2workspace_cli/app.py`.
- Normal CLI sessions create isolated project-root workspaces by default at
  `workspace/<YYYYMMDDHHMMSS>`.
- Experiment runners with fixed repo-layout assumptions currently opt out and
  keep their original working directories, notably `experiments/oneshot` and
  `experiments/skill_tests`.
- The local gateway responds through chat-completions compatibility, but the
  full agent path still is not confirmed for the ideal Responses API mode.

Remaining gaps:

- decide whether tracked `.env` should become `.env.example` before publication
- revisit `use_responses_api = true` only if the local gateway later supports
  the full tool-calling flow cleanly

### 6. Report Runtime

Status: report requests run through the supervisor-first report family

- Formal report requests now use the report family inside Supervisor Graph:
  `init_report -> monitoring_lane -> local_data_lane -> literature_lane -> compose_report -> summarize`.
- Report execution no longer depends on a dedicated `multi-source-report`
  project skill. The active path is the report family runtime plus
  `.code2workspace/skills/orchestration/supervisor-guidance/` report guidance.
- The current report lane design still emphasizes:
  - authoritative monitoring and surveillance evidence
  - local structured data or API evidence where available
  - literature / technical / primary-source web evidence
  - a final composition step that preserves uncertainty and explicit evidence
    gaps
- Focused validation currently recorded:
  - `libs/code2workspace/tests/unit_tests/test_orchestration_runtime.py`
  - `libs/cli/tests/unit_tests/test_supervisor_runtime.py`
  - report routing trigger replays under
    `experiments/harness/runs/supervisor-routing-trigger-eval/`
  - bounded report-case replays under
    `experiments/harness/runs/supervisor-report-cases-bounded/`

Remaining gaps:

- report routing is stable, but live bounded runs still often stall in
  `init_report` or before all three evidence lanes finish
- the report pipeline still needs stronger final-body completion and better
  latency on composition-heavy prompts
- a chart/image pipeline still does not exist; current report enhancement is
  still text/table-first rather than figure-first

## Main Blockers

- heavy scientific repositories are expensive and slow to converge on cold
  Docker layers
- the Web Workbench metadata store and CLI/TUI runtime state are still not
  perfectly unified
- gateway compatibility with the ideal Responses API path is incomplete
- the inherited runtime is usable, but the repo-specific `code2workspace`
  pipeline still needs more implementation depth

## Current Priority Order

1. Continue hardening and running the generic one-shot experiment path.
2. Turn the prompt/policy surfaces into repeatable harness experiments.
3. Keep the Web Workbench useful but thin.
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
  `workspace/<timestamp>` below the project root when launched inside a
  project, while fixed-layout experiment runners explicitly preserve their
  original cwd.
- Fixed a web-store concurrency issue by enabling SQLite `WAL` mode and busy
  timeout handling so repeated status polling no longer leaves quick one-shot
  runs stranded in `running`.
- Later work reintroduced a checked-in Web Workbench frontend under
  `apps/webapp/frontend/`; treat the current web architecture as
  frontend-plus-backend-plus-proxy.
- Rebased the local benchmark helper and catalog onto `experiments/benchmark/`,
  updated the seven local covid-assembly case inputs to live paths, and started
  a real benchmark run with partial WDL-positive results for `spades`,
  `megahit`, and `trinityrnaseq`.
- Added a soft planner-routing layer for project skills:
  - `planning-guide` now emits structured soft recommendations such as
    `recommended_skill`, `selected_skill`, task type, lane hints, and fresh-run
    isolation hints for obvious benchmark / github2workspace prompts
  - the shared CLI agent path now injects those recommendations into the
    system prompt via a planner middleware instead of forcing hard dispatch
  - isolated copies can now point back to the original project root through a
    `.code2workspace/project-root.txt` marker so project skills and agents stay
    visible without copying historical `results/`
  - the planning contract now also carries task-specific execution constraints
    such as fresh-output requirements, no-reuse hints, shared-dataset
    preference, strict phase gates, lane dependencies, and final synthesis /
    report expectations
  - the repo-to-workspace orchestration line now centers on
    `github2workspace` naming instead of the older `paper2workspace` alias

### 2026-04-22

- Added stable `Planner:` / `Planner Contract:` summaries to non-interactive
  CLI logs so planner recommendations are visible and testable even in quiet
  mode.
- Upgraded the checked-in harness config from a two-case demo to the live
  `train/holdout` repo split with fixed `stratum` labels.
- Added four low-cost project-skill orchestration eval cases covering:
  benchmark routing, github2workspace routing, mixed-task lane summaries, and
  phase-gated workspace report generation.
- Recorded initial real smoke results:
  - benchmark routing: `passed`
  - github2workspace routing: `passed`
  - mixed-task routing: `passed`
  - phase-gated report helper: `passed`
  - unified result root:
    `results/skill-tests/project-skill-orchestration/20260422`

### 2026-04-23

- Reworked report orchestration around a supervisor-managed lane workflow and
  local evidence skills.
- Added focused unit coverage and live report-oriented skill-test cases for the
  branch's then-current report surface.
- Tightened formal report composition so numeric evidence could be rendered as
  source-backed Markdown tables when reliable enough, while weak numeric
  fragments were explicitly left un-tabulated.

## Read Next

- `docs/overview/roadmap.md`
- `docs/overview/session-handoff.md`
- `apps/webapp/README.md`
- `experiments/oneshot/README.md`
- `experiments/harness/README.md`
