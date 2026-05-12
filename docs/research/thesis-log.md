# Thesis Log

This file records repository evolution as thesis material.

For the engineering-facing current snapshot, read
`docs/overview/current-status.md`. For thesis drafts and chapter assets, start
from `docs/research/README.md`.

## Working Thesis Direction

Design and implementation of a LangGraph-based agent system that converts
software repositories into runnable workspaces and executes structured software
engineering and scientific-workflow tasks through Supervisor Graph orchestration
and evidence-backed completion judgment.

## Research Themes

- agent-oriented workspace interaction
- one-shot execution for long-running repository tasks
- reproducible experiment logging
- Supervisor Graph orchestration and node-level evidence
- evidence-backed completion judgment
- frontend and runtime integration for controllable agent workflows

## Chronology

### 2026-05-12

- Unified Supervisor Graph worker execution behind an explicit runner boundary:
  - added `SupervisorWorkerRunner` and runnable-backed worker dispatch in
    `libs/cli/code2workspace_cli/supervisor_runtime.py`
  - changed `create_cli_agent()` so supervisor nodes use a dedicated worker
    agent runnable while the original base agent remains available as fallback
  - preserved deterministic benchmark helpers as first-priority adapters before
    normal worker-agent dispatch
- Fixed a subagent middleware construction issue so regular subagents are
  compiled into the `task` tool even when no HITL `interrupt_on` config is set.
- Validation: focused supervisor, agent assembly, and subagent tests passed
  (`test_supervisor_runtime.py`, `test_agent.py`,
  `test_subagent_middleware_init.py`, and `test_subagents.py`).

### 2026-05-10

- Strengthened the generic Supervisor Graph execution contract rather than only
  the graph skeleton:
  - expanded `libs/cli/code2workspace_cli/supervisor_capabilities.py` so each
    capability bundle now carries a structured execution contract
    (`execution_focus`, `preferred_inputs`, `expected_outputs`,
    `stop_condition`, `avoid`)
  - added `generic_qa` family guidance plus node guidance assets for
    `init_generic`, `worker_context`, `worker_solution`, and `compose_generic`
  - changed generic classification so normal generic tasks also carry the
    `generic_qa` guidance id instead of relying only on QA-only wrapper
    overrides
- This matters methodologically because the earlier generic path had a decent
  skeleton but relatively weak worker contracts; after this change the generic
  nodes receive more explicit bounded-execution instructions, which is closer to
  the intended "shallow orchestration + evidence-backed answer" design.
- Added a small repeatable multi-case evaluation script
  `experiments/harness/evaluate_generic_capability_prompts.py` and generated the
  first artifact set under
  `experiments/harness/runs/generic-capability-prompt-eval/20260510T174323Z/`.
- Validation:
  - targeted generic/runtime tests passed (`44 passed`)
  - broader CLI/config/agent/supervisor regression suite passed (`632 passed`)
  - the five business cases in the new capability-prompt evaluation all kept
    the generic graph and all showed the expected family guidance plus richer
    capability-contract fields

- Split a QA-only supervisor-runtime branch for a portable question-answering
  form of the current agent rather than creating a separate simple bot:
  - added the single main-agent config entry
    `backend/config/agent_models.json`
  - disabled `.env` loading for the main runtime path
  - changed default sessions to inherit the launch directory instead of
    creating `workspace/<timestamp>`
  - made remote sandbox startup fail fast in the QA-only CLI path
  - added a `runtime.mode = "qa"` switch that forces Supervisor Graph routing
    through the generic QA graph while preserving the base worker/supervisor
    structure
- Validation: focused configuration, non-interactive, and supervisor runtime
  tests passed (`421 passed`, warnings only).

### 2026-05-08

- Cleaned the thesis-facing documents so the formal paper no longer presents
  the local harness loop as a thesis method:
  - rewrote `THESIS_FULL_DRAFT_ZH.md` around Supervisor Graph orchestration,
    node-level artifacts, and evidence-backed completion judgment
  - removed the old surface/variant/keep-discard story from the outline, asset
    matrix, experiment-design notes, method draft, chapter draft, appendix
    templates, task book, and proposal
  - updated thesis asset-note wording so generated notes discuss execution
    bottlenecks and standardized evidence rather than harness decisions
  - remaining `harness` matches in thesis files are path names under the
    existing `experiments/harness/` directory

- Reworked the thesis-facing narrative so the current `supervisor-graph-runtime`
  branch is presented as supervisor-first rather than as "one-shot as the inner
  execution path":
  - updated `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so chapter 3 now
    describes the base worker agent being wrapped by Supervisor Graph, chapter 4
    uses the current `init_generic -> worker_context -> worker_solution ->
    compose_generic -> summarize` generic graph, and chapter 5 treats one-shot
    only as the historical baseline / batch-launch layer
  - replaced the old project-skill / soft-routing thesis tables with
    Supervisor-Graph-facing table slots for routing-trigger evidence and generic
    real replays
  - aligned `THESIS_OUTLINE_ZH.md`, `THESIS_ASSET_MATRIX_ZH.md`,
    `THESIS_EXPERIMENT_DESIGN_ZH.md`, `THESIS_METHOD.md`, `THESIS_CHAPTER_ZH.md`,
    `README.md`, and `docs/overview/supervisor-system-architecture.md` to the
    same thesis framing
  - intentionally excluded the `report` family from the thesis diagrams,
    tables, and experiment narrative even though the runtime still supports it
- Updated the thesis asset-notes helper and its focused tests so the generated
  table notes now match the revised chapter-5 numbering:
  - table 5-5: Supervisor Graph routing-trigger results
  - table 5-6: Supervisor Graph generic real replays
  - table 5-7: two-hour reduced evaluation
  - table 5-8: benchmark snapshot
- Validation:
  - `experiments/harness/tests/test_thesis_asset_notes.py`: `3 passed`
  - `experiments/harness/tests/test_code2workspace_harness.py`: `11 passed`
  - regenerated `experiments/harness/code2workspace_毕业论文.docx`
  - regenerated thesis asset notes via `generate_thesis_asset_notes.py`

- Updated the thesis and overview documents to reflect the current
  `apps/webapp` implementation as a full Web Workbench rather than only a
  small backend service:
  - Starlette serves the built Next.js `agent-chat-ui` frontend
  - `/langgraph/*` proxies browser chat traffic to a shared local LangGraph
    server started through the CLI server bridge
  - `/api/*` remains as management routes for settings, threads, history,
    workspace files, run state, interrupts, and decisions
- Reworked the chapter-3 Web control-plane narrative, architecture/data-flow
  Mermaid diagrams, thesis outline, and asset matrix accordingly, then
  regenerated both thesis DOCX outputs.

- Re-applied the compact technical-principles section on top of the synchronized
  `test-agent-8081` thesis baseline while preserving the restored paragraph
  version of `1.4 研究问题与挑战`.
- Chapter 2 is again `相关技术基础与系统需求分析`; the new `2.1` covers LLM
  agents/tool use, LangGraph/LangChain, Docker/WDL/Cromwell, and
  harness/benchmark evidence-based evaluation, with the original requirement
  sections shifted to `2.2`-`2.6`.
- Updated `experiments/harness/THESIS_OUTLINE_ZH.md` and
  `experiments/harness/generate_thesis_docx.py`, then regenerated both thesis
  DOCX outputs from the current markdown.

- Synchronized the active thesis-related harness documents from the
  `test-agent-8081` worktree back into the supervisor-runtime worktree:
  `THESIS*.md`, `generate_thesis_docx.py`, and the two generated thesis DOCX
  files. This restores the paragraph-style `1.4 研究问题与挑战` section and the
  chapter-2 `系统需求分析` structure from that version as the active thesis
  baseline.
- Validation: verified the synchronized files match the source worktree
  byte-for-byte and ran a temporary DOCX generation smoke test with
  `generate_thesis_docx.py`.

- Added a compact technical-principles section to the thesis draft after
  comparing the current structure against common engineering-thesis patterns:
  chapter 2 is now `相关技术基础与系统需求分析`, with `2.1` covering LLM
  agents/tool use, LangGraph/LangChain, Docker/WDL/Cromwell, and
  harness/benchmark evidence-based evaluation before the requirement analysis.
- Synchronized `experiments/harness/THESIS_OUTLINE_ZH.md` with the new chapter
  2 structure, appended LangGraph/LangChain documentation references, and
  regenerated `experiments/harness/code2workspace_毕业论文_新版结构.docx`.

- Adjusted the thesis draft so `benchmark` is presented as a first-class system
  scenario alongside `github2workspace`, rather than mainly as a chapter-5
  experiment result.
- Updated `experiments/harness/THESIS_FULL_DRAFT_ZH.md` so chapter 2 now
  defines two core task families:
  - `github2workspace`: repository-to-runnable-workspace execution
  - `benchmark`: shared-dataset registration, tool selection, parallel case
    execution, and metric summarization
- Updated chapter 3 to include benchmark inputs, dataset registration, case
  fan-out, metric summaries, and benchmark artifacts in the overall system
  architecture and execution-flow narrative.
- Reworked chapter 4 into a key-mechanism chapter where Supervisor Graph is
  described as the shared orchestration framework for both sequential
  `github2workspace` graphs and shared-input parallel `benchmark` graphs, with
  node-level replanning and failure handling described separately for each.
- Regenerated the thesis DOCX draft
  `experiments/harness/code2workspace_毕业论文_新版结构.docx` from the updated
  markdown using a temporary `python-docx` dependency injection.
- Validation: thesis/harness focused tests passed
  (`experiments/harness/tests/test_thesis_asset_notes.py` and
  `test_code2workspace_harness.py`, `14 passed`).

### 2026-05-07

- Reworked the generic branch of the Supervisor Graph planner so it is no
  longer modeled as a thin `analyze_task` placeholder followed by a separate
  execution round.
- The generic task family now defaults to a graph that better matches the
  intended runtime behavior:
  - `init_generic`
  - `worker_context`
  - `worker_solution`
  - `compose_generic`
  - `summarize`
- This matters methodologically because the earlier generic graph overstated a
  planner-only decomposition and understated the intended first-layer worker
  fan-out. The new graph makes the generic path more comparable to the
  report-style `init -> lanes -> compose` pattern while preserving a normal
  user-facing answer rather than a formal report artifact.
- Tightened task-family disambiguation at both levels:
  - rule fallback now keeps prompts containing cues such as `不要正式写作`,
    `口头判断`, and `区分证据和猜测` on the generic path
  - the LLM classifier prompt now also states that such prompts should remain
    generic unless they still clearly demand a formal deliverable
- Focused validation passed for the updated runtime and CLI supervisor test
  suites (`37 passed` on the scoped worktree tests).
- A fresh generic-only routing-trigger replay under
  `experiments/harness/runs/supervisor-routing-trigger-eval/20260507T143455346391Z/`
  now shows `5/5` correct generic classifications with the new
  `init_generic -> worker_context -> worker_solution -> compose_generic ->
  summarize` graph skeleton. That replay used rules fallback because the paid
  relay credentials were absent in the shell, so a credentialed rerun is still
  needed before attributing the improvement to the hybrid classifier rather
  than to the fallback rules alone.

### 2026-05-06

- Reorganized the benchmark dataset layer so it no longer reads as if the whole
  benchmark surface were only `新冠病毒组装`:
  - restored a checked-in `experiments/benchmark/datasets/benchmark_catalog.json`
    in the current worktree after that local copy had gone missing
  - added benchmark-family README guides for `experiments/benchmark/`,
    `cirrna/`, and `免疫逃逸/`
  - extended the dataset registry with shared-dataset candidate bundles for
    circRNA and immune-escape tasks
- This matters for the thesis because it sharpens an experimental-design
  distinction that was previously blurred in the repository layout:
  - virus assembly tools can often share one raw-read dataset per family
  - circRNA tools can share RNA-seq plus reference bundles, but many still need
    derived intermediate artifacts such as SAM/BAM or junction lists
  - immune-escape tools are more heterogeneous still, so a fair benchmark
    should share a layered evidence bundle (`DMS` tables plus
    structure/sequence assets) rather than pretending one uniform raw input
    exists for all tools
- The new candidate shared datasets are intentionally pragmatic rather than
  overclaimed:
  - `circrna-hela-rnaser-paired`
  - `circrna-blood-prjna722046`
  - `immune-escape-rbd-functional-dms`
  - `immune-escape-rbd-antibody-escape`
  - `immune-escape-covabdab-structural-bundle`
- Methodologically this is useful because it makes the next benchmark extension
  step explicit: before wiring new task families into the supervisor helper,
  the repository now has a documented shared-dataset layer to anchor tool
  selection and input fairness decisions.

### 2026-05-05

- Adjusted the normal CLI session workspace policy on the supervisor-runtime
  branch so project-launched interactive and non-interactive sessions now create
  timestamped workspaces under the project root's `workspace/` directory rather
  than under whichever subdirectory the user invoked the CLI from.
- This keeps supervisor orchestration artifacts comparable across TUI,
  non-interactive, and resumed-thread runs while preserving the explicit
  `inherit` mode for fixed-layout experiment runners.

- Removed another set of no-longer-authoritative branch-local assets after the
  latest real `github2workspace` and `report` traces confirmed they were not on
  the live execution path:
  - deleted the checked-in report-only project subagents under
    `.code2workspace/agents/`
  - deleted the retired harness-side `OpenClaw` / `ACPX` bridge bundle under
    `experiments/harness/skills/openclaw/` plus its importer/tests
  - rewrote the remaining live report/evidence skill prompts so they no longer
    point at `report_agent` or named report-only subagents
- This matters for the thesis because it removes one more surface-level
  contradiction between the codebase narrative and the observed runtime:
  - the validated branch now reads more consistently as `supervisor` planning,
    generic workers executing, and evidence artifacts carrying state
  - the remaining project skills now look like evidence/tooling helpers rather
    than like competing orchestration shells or external-agent bridges

- Pruned another set of no-longer-authoritative orchestration surfaces on the
  current supervisor-runtime branch:
  - removed the dead `paper2workspace` project-skill shell
  - removed the unused CLI `planner_routing.py` middleware path and its direct
    tests
  - removed the thin `github2workspace-orchestrator` wrapper Skill and kept the
    task family represented directly in the supervisor graph/runtime instead
- This matters for the thesis because it reduces a remaining architectural
  ambiguity:
  - previously, the codebase still contained both the new explicit
    supervisor/worker graph and several older skill-wrapper surfaces that looked
    like alternative orchestrators
  - after this cleanup, the narrative is clearer: `supervisor` is the planner,
    `worker` is generic, and project Skill assets are optional helpers or
    guidance rather than competing runtime entrypoints
- Kept `planning-guide` only as an optional local planning helper, but removed
  its dependency on the deleted `github2workspace` wrapper so repository-task
  planning no longer points back at a retired orchestration facade.

- Root-caused a concrete supervisor-runtime failure mode in the live benchmark
  path: the non-interactive CLI was starting the local `langgraph dev` server
  without `--allow-blocking`, while the new supervisor layer uses synchronous
  file I/O, SQLite case-index rebuilds, and deterministic helper subprocesses.
- This matters methodologically because it separates two different causes of
  “agent stall” that would otherwise be conflated in the thesis:
  - runtime/scheduler incompatibility with blocking orchestration code
  - model-level failure to stop and return control after enough work is done
- Fixed the first issue by changing the CLI server startup path to include
  `--allow-blocking` for local dev runs, then addressed the second issue for the
  benchmark family by adding deterministic helper-backed fast paths for
  `register`, `spades`, `megahit`, and `summarize` inside the supervisor worker
  runtime.
- This is useful thesis evidence because it shows a hybrid orchestration design
  becoming more explicit:
  - the generic supervisor / worker graph still exists
  - but a subset of known benchmark nodes now bypass open-ended model behavior
    and execute checked-in helper contracts directly when the path is already
    well understood
- Focused verification covered:
  - new server-helper regression that enforces `--allow-blocking`
  - new supervisor-runtime regressions for deterministic benchmark register,
    repo-node execution, and summary behavior
  - combined targeted suite result: `23 passed`
- Fresh live evidence now shows the benchmark chain advancing further than
  before:
  - run root:
    `workspace/20260505145718/orchestration_runs/20260505T065722Z`
  - `register` now finishes immediately and writes the expected helper-first
    scaffold (`benchmark_plan`, `dataset_resolution`, `metric_plan`, per-case
    `execution_ready`)
  - the remaining runtime budget is now dominated by real SPAdes execution cost
    rather than by the earlier first-node supervisor stall
- Tightened the benchmark execution semantics after confirming that synchronous
  deterministic helpers could still serialize nominally parallel ready nodes by
  blocking the async event loop.
- The worker invocation path now runs deterministic benchmark helpers in a
  worker thread, preserving the existing dependency-aware `asyncio.gather`
  scheduler while allowing `spades` and `megahit` to execute concurrently after
  `register`.
- Added a regression test that uses blocking fake deterministic workers and
  asserts both ready benchmark branches are active at the same time; the focused
  supervisor/orchestration suite now passes with `19 passed`.
- A fresh full two-tool run provides end-to-end evidence for the intended
  supervisor shape:
  - run root:
    `workspace/202605051600_parallel/orchestration_runs/20260505T081847Z`
  - `tool_activity.jsonl` records `register` completing, then `spades` and
    `megahit` both starting before either branch finishes
  - the run completes in one round with `decision=stop`, `failed_nodes=[]`, and
    `reason=All nodes completed.`
  - metrics remain available for both completed cases:
    `megahit` has `contig_count=472`, `assembly_size=4530520`, `n50=18360`;
    `spades` has `contig_count=1191`, `assembly_size=4582516`, `n50=24099`
- Re-ran the same prompt through the outer non-interactive CLI entrypoint:
  - run root:
    `workspace/20260505165456/orchestration_runs/20260505T085500Z`
  - it preserved the same fan-out event order and completed with
    `decision=stop`, `failed_nodes=[]`, and `reason=All nodes completed.`
- Tested a less prescriptive benchmark prompt that only provided the benchmark
  path, the `short-read-ecoli-srr001666` dataset, and target metrics
  (`contig_count`, `assembly_size`, `n50`) while leaving tool choice to the
  agent:
  - run root:
    `workspace/20260505185712/orchestration_runs/20260505T105716Z`
  - the planner still selected the appropriate short-read assembly pair
    `spades` and `megahit`
  - execution preserved the same parallel worker event order and completed
    `2/2` cases
- That natural-prompt test exposed a reporting gap: the system had enough
  metric evidence but did not directly answer which tool looked better. The
  deterministic summary path now writes an explicit comparison object and
  Markdown section; for the observed metrics it favors `spades` by N50 and
  assembly size while noting that `megahit` has lower `contig_count`.
- Removed the remaining tool-specific benchmark coupling from the supervisor
  runtime and guidance assets:
  - planner tool selection now reads the benchmark catalog and follows the
    selected dataset's shared-compatible tool list instead of relying on a
    hardcoded default pair
  - per-case expected output checks now read each case manifest rather than a
    runtime-local output-name table
  - tool-specific node guidance was replaced with one generic
    `benchmark_case` guidance artifact
- The same natural prompt was rerun after decoupling:
  - run root:
    `workspace/20260505212743/orchestration_runs/20260505T132747Z`
  - it still completed `register -> parallel per-case workers -> summarize`
    with `decision=stop` and `failed_nodes=[]`
  - the final answer includes the metric judgment that `spades` is favored by
    N50/assembly size while `megahit` has lower contig count
- After the benchmark catalog/readmes were deleted to test a more autonomous
  setting, a long-read natural prompt exposed the next design gap:
  - run root:
    `workspace/20260506092525/orchestration_runs/20260506T012529193142Z`
  - the graph classified the task as `benchmark` but had no selected tools
  - deterministic `register` failed with `missing_selected_tools`, and summary
    only produced an empty partial result
- This is useful thesis evidence because it separates "no hardcoded tool names"
  from true autonomous benchmark planning: the current implementation can avoid
  `spades`/`megahit` coupling, but still needs either a catalog-like structured
  source or a model/asset-inspection register step that can create the fan-out
  graph itself.

### 2026-04-30

- Replaced the earlier long-task soft-routing default with a first explicit
  supervisor-graph runtime, then generalized it further so all tasks now enter
  that layer and known families only contribute guidance/templates.
- The new split is architecturally cleaner:
  - `supervisor` now plans graph rounds, retrieves prior similar cases,
    evaluates node outcomes, and decides whether to stop or replan
  - `worker` is now one generic execution contract rather than several
    report/build-specific role abstractions
  - unknown tasks now also receive a structured default graph instead of
    bypassing supervisor entirely
  - graph artifacts are persisted under each thread workspace so the runtime
    history is inspectable and replayable
- This matters for the thesis because it turns the orchestration layer from a
  prompt-guided behavior into an explicit machine-readable control structure:
  - graph nodes, edges, worker outputs, and supervisor decisions are now
    serializable experiment artifacts
  - benchmark and repository-to-workspace tasks can now be analyzed as graph
    execution traces rather than only as chat logs
- Added a rebuildable SQLite case index over canonical workspace artifacts.
  Methodologically this is important because historical runs now become a
  retrieval input to later supervisor planning instead of only a post hoc log.
- Added a config-level OpenAI alias provider so the project can keep two
  distinct OpenAI-compatible relays side by side:
  - `openai` for the earlier self-hosted relay
  - `openai_paid` for the newer paid relay, now set as the user-level default
- This is useful thesis evidence because it separates two confounded variables:
  - orchestration/runtime behavior
  - provider/relay responsiveness and compatibility
- Focused verification covered:
  - new runtime unit tests for graph planning/execution
  - new CLI runtime tests for artifact writing, replan behavior, and case-index
    rebuild/search
  - the existing targeted CLI/runtime regression suite (`175 passed`)
  - focused TUI startup unit checks (`3 passed`)
  - repeated real CLI smokes on the external `openai:gpt-5.4` path, which
    showed mixed environment-dependent behavior: one earlier run exited
    successfully, while a later 30-second rerun timed out
- One remaining caution is also useful thesis evidence:
  - the live external-provider non-interactive smoke is not yet fully stable,
    so runtime evaluation must still distinguish between orchestration
    correctness and provider/network variance
  - under scripted capture, the real interactive TUI startup smoke still timed
    out before a clean `Ready to code!` style closeout
  - the focused startup unit checks still pass, so the remaining issue is now
    narrower than “TUI is broken”; it is specifically about startup behavior
    under this captured environment and should be investigated separately

### 2026-04-23

- Reworked the repository's report-generation surface from two partially
  overlapping skills into one explicit multi-source report lane:
  - removed `deep-research-report`
  - removed `epidemic-warning-report`
  - added `multi-source-report` as the single report-writing entrypoint
  - replaced the old report-specific project subagents with
    `report-researcher`, `report-synthesizer`, and `report-web-researcher`
- This matters for the thesis because it removes a design ambiguity that would
  otherwise weaken the narrative about what the system is actually optimizing:
  - before this change, "deep research" and "warning report" were separate
    skill surfaces with overlapping responsibilities
  - after this change, the optimization object is clearer: one report
    orchestrator, multiple evidence lanes, and one shared report artifact
    contract
- The new `multi-source-report` lane also pulls the report architecture closer
  to the `deepagents` deep-research pattern while still grounding it in the
  local repository evidence stack:
  - plan / init / parallel lane research / synthesis / compose / verify
  - first-class evidence layers remain the project's own skills and local
    sources rather than a pure web-search setup
- This is useful thesis evidence because it clarifies a hybrid design pattern:
  - the orchestration pattern is borrowed from a frontier agent framework
    (`deepagents`)
  - but the evidence sources are intentionally local/project-specific, which is
    important for controlled experiments and source traceability
- Focused validation now covers the new consolidated report surface:
  - discovery and routing tests now recognize `multi-source-report` instead of
    the two earlier report skills
  - nested subagent scope-guard tests now use `multi-source-report`
  - the new helper tool tests verify both a general report mode and a
    risk-oriented mode
  - live skill-test runs now leave real artifact evidence under:
    `results/skill-tests/20260423-msr-behavior/`,
    `results/skill-tests/20260423-msr-structure/`, and
    `results/skill-tests/20260423-msr-e2e/`
- Methodologically, this helps the thesis in two ways:
  - it makes report generation easier to evaluate because artifact layout,
    lane names, and diagnostics are now unified
  - it creates a cleaner bridge between "research-like" agent behavior and
    "formal report-writing" agent behavior, which were previously split across
    two skill identities
- Tightened the formal-report output contract one step further after the skill
  consolidation:
  - formal `multi-source-report` runs now default to long-form output
    (`5000+` Chinese characters)
  - lanes may now emit structured `Table Candidate:` blocks for reliable
    numeric evidence
  - the compose step turns those into a deterministic `Key Data Tables`
    Markdown section with source/time/scope columns
  - if the numeric evidence is incomplete or non-comparable, the report now
    states that no reliable table could be produced instead of inventing one
- This is useful thesis evidence because it improves the interpretability of
  the report artifact without needing a full visualization pipeline:
  - the report can now surface key comparative values in a reproducible format
  - the diagnostics explicitly distinguish between “no numeric evidence” and
    “numeric evidence exists but was too weak to tabulate”
  - this gives a cleaner evaluation target for future work on charts or richer
    report presentation

- Continued the real eight-repository harness optimization loop, but the next
  train rerun showed a more specific bottleneck than the earlier
  prompt-surface-only picture:
  - run root:
    `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T153031Z`
  - the train score stayed at `3/5`, yet the failure pattern changed
    materially:
    - passed: `spades`, `Flye`, `trinityrnaseq`
    - failed: `canu`, `megahit`
  - both misses now failed via early `RemoteException` /
    `RemoteProtocolError` internal errors rather than by simply never finding a
    runnable repository path
- This is useful thesis evidence because it separates two different outer-loop
  levers that would otherwise be conflated:
  - prompt shaping can change the agent from “reading too long” to “starting
    real execution earlier”
  - but once prompt behavior improves, the next ceiling may be runtime
    stability rather than prompt quality
- Root-caused and fixed two more measurement/stability issues after that rerun:
  - added a one-shot runner retry for narrow transient remote/internal errors,
    preserving the first failure as `agent.retry1.log` and rerunning once under
    the same total runtime budget
  - widened the completion judge so container validation is no longer limited
    to a small hard-coded set of log filenames such as `docker_run.log`; real
    execution logs like `docker_canu_meryl.log` now count
- This is again useful thesis evidence because it distinguishes three classes
  of “failure” inside the same harness:
  - true repository/task failures
  - transient platform/runtime failures
  - evaluator false negatives caused by too-narrow success evidence contracts
- Collected live post-fix repo-level evidence outside the train split to verify
  the new hypotheses before paying for another full harness cycle:
  - `results/oneshot-repro/megahit/20260422T201219Z` now reaches a full real
    completion again
  - `results/oneshot-repro/canu/20260422T201219Z` reaches real Docker plus WDL
    success, and its original `completed=false` summary is explained entirely
    by the old docker-log-name judge gap; under the fixed judge it recomputes
    as `completed=true`
- A fresh train rerun with both fixes applied is now in progress under
  `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T203210Z`.
  This is the first train cycle positioned to answer the more precise thesis
  question: how much of the remaining miss set was due to transient runtime
  instability plus evaluator undercount, rather than to task-planning quality
  alone?
- That train rerun has now settled and gives a clearer answer:
  - persisted result: `4/5`
  - repository-level outcomes:
    - pass: `spades`, `canu`, `megahit`, `Flye`
    - persisted miss: `trinityrnaseq`
- The remaining `trinityrnaseq` miss is not a true execution failure:
  - the real run produced fresh `cromwell_run_retry2.log`,
    `metadata_retry2.json`, and real WDL output artifacts
  - after generalizing the completion judge from fixed retry filenames to
    fresh `cromwell_run*.log` and `metadata*.json`, the exact same persisted
    artifacts recompute as `completed=true`
- This is useful thesis evidence because it shows another distinct class of
  harness undercount:
  - not only can the evaluator be too narrow about file locations or log names
  - it can also be too narrow about retry numbering conventions even when the
    underlying scientific workflow actually succeeded
- Under the current code semantics, the train split is therefore effectively
  `5/5`, not `4/5`.
- Ran the next holdout rerun with the same runner and evaluator fixes under
  `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260423T023441Z`:
  - persisted result: `2/3`
  - pass: `v-pipe`, `covid-19-signal`
  - fail: `fieldbioinformatics`
- The important new holdout evidence is that `v-pipe` flipped from a persistent
  holdout miss into a full real Docker + WDL pass after the harness changes.
  This is useful thesis material because it shows the fixes were not merely
  overfit to the train repositories.
- The repository-wide picture is now:
  - persisted totals: `6/8`
  - effective totals under the updated completion code: `7/8`
  - only remaining clear miss: `fieldbioinformatics`
- This narrows the next thesis-relevant optimization step substantially:
  the outer loop no longer needs broad prompt or runtime surgery first; it can
  focus directly on why `fieldbioinformatics` still fails to transition from
  early repository inspection into real artifact-producing execution.
- Follow-up isolated repros further narrowed the remaining miss:
  - one retry on transient remote/internal agent failures was still not enough
    for `fieldbioinformatics`, so the one-shot runner now allows two such
    retries
  - after those retries, the repo can be pushed through real Docker build,
    real container validation, and into real Cromwell execution
  - the current repo-level failure is therefore no longer “the agent never gets
    going”, but a narrower Cromwell-shell-environment issue: the image is
    started under `/bin/bash`, which bypasses environment activation and leaves
    `artic` unavailable on `PATH`
- This is useful thesis evidence because it shows the remaining gap is now a
  specific integration-contract problem between image construction and the WDL
  execution model, not a general prompting or runtime-collapse problem.

### 2026-04-22

- Added a thesis-facing asset-index / regeneration line so checked-in
  experiment outputs can be turned directly into manuscript-ready tables and
  figure notes:
  - `docs/research/experiment-artifact-index.md` now indexes the currently
    usable thesis-facing result bundles
  - `experiments/harness/generate_thesis_asset_notes.py` and
    `experiments/harness/tests/test_thesis_asset_notes.py` provide
    caption-ready notes for the current table / figure set
  - `results/thesis-asset-notes-20260422/`,
    `results/oneshot-baseline-summary-20260422/`, and
    `results/thesis-plot-data-20260422/` now serve as the current manuscript
    asset bundles rather than requiring manual value extraction
- Added and validated a real `SWE-bench Lite` pilot line under
  `experiments/swebench/`:
  - runner: `run_swebench_lite_pilot.py`
  - summarizer: `summarize_swebench_lite.py`
  - thesis-facing summary bundle:
    `results/swebench-lite-summary-20260423/`
  - the checked-in pilot now covers five real dev-split instances with
    evidence for resolved, unresolved, and empty-patch / service-instability
    outcomes
- This matters for the thesis because it adds a second evaluation layer beyond
  the bioinformatics repository tasks:
  - `SWE-bench Lite` provides a recognizable software-engineering benchmark
    anchor
  - the repo-to-workspace and scientific-workflow tasks still provide the
    domain-specific execution / harness evidence
- Tightened the manuscript and chapter assets so they now point at those real
  generated bundles instead of ad hoc notes:
  - `THESIS_FULL_DRAFT_ZH.md`
  - `THESIS_EXPERIMENT_DESIGN_ZH.md`
  - `THESIS_ASSET_MATRIX_ZH.md`
  - `docs/research/README.md`

- Added a harness-native phase-1 benchmark-autonomy ladder under
  `experiments/harness` so the repository can study how much agent freedom is
  tolerable before benchmark reliability drops:
  - `level1`: fixed WDL + fixed tools + fixed datasets
  - `level2`: fixed WDL + agent-chosen tools + fixed datasets
  - `level3`: fixed WDL + agent-chosen tools + agent-chosen input files
  - `level4`: run-local editable WDL + agent-chosen tools + agent-chosen input
    files, with direct-source WDL editing recorded as an optional subvariant
- Kept the first ladder intentionally narrow to make the thesis experiment
  easier to interpret:
  - only the assembly families are in scope
  - short-read family: `spades` and `megahit`
  - long-read family: `canu` and `Flye`
  - `trinityrnaseq` and the viral workflows are explicitly deferred so
    reference/model/network confounders do not pollute the first autonomy study
- Implemented isolated benchmark staging instead of relying on the original
  repository tree at execution time:
  - each run now copies only the required benchmark WDL/input assets and staged
    dataset files into a fresh workspace-local `experiments/benchmark` tree
  - the workspace writes `.code2workspace/project-root.txt` so the original
    project skills remain visible without copying historical `results/`,
    `.workspaces/`, or earlier `workspace/` artifacts
  - this is useful thesis evidence because it turns the earlier “agent looked
    at history” concern into a controlled experimental variable
- Added report-first benchmark-autonomy outputs at the harness layer:
  - the agent prompt now requires both a machine-readable JSON report and a
    Markdown report before optional extra retries
  - the harness also writes its own fallback `summary.json` / `summary.md`
    after each run so partial executions still leave a comparable record with
    selected tools, selected inputs, WDL-change state, basic cost counters, and
    normalized failure taxonomy
- Focused validation now covers the new ladder contract, isolated staging,
  prompt-policy differences across the four levels, report synthesis, and the
  new CLI `validate-benchmark-autonomy` entrypoint.
- Ran the autonomy ladder far enough to establish a useful engineering pattern
  before stopping further expansion:
  - `short-read-assembly` completed successfully at levels 1-4
  - `long-read-assembly` completed at levels 1-2 with `canu` success and
    reproducible `Flye` image-packaging failure
  - even when WDL editing became allowed at level 4, the agent did not choose
    to modify the staged WDL copies; it continued to prefer direct Docker
    execution of the staged task commands
- Shifted the next harness theme back toward the thesis-critical “real repo
  task” surface instead of continuing the autonomy ladder indefinitely:
  - added a simple eight-repository harness config driven by
    `experiments/harness/configs/repo_splits.toml`
  - kept the train/holdout split explicit: five assembly-heavy repositories in
    train and three virus/workflow repositories in holdout
  - reused the existing one-shot prompt and completion rubric so later
    optimization results remain directly attributable to known surfaces rather
    than to a new execution stack
- Ran the first real train baseline on that eight-repository harness surface:
  - run root:
    `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T090923Z`
  - persisted train result: `1/5` completed, with `trinityrnaseq` as the first
    recorded pass
  - the run also produced high-signal failure classes instead of just “not
    enough passes”:
    - `spades` entered real execution and then hit a remote protocol/internal
      agent error mid-run
    - `canu` exited without producing fresh Docker/WDL artifacts
    - `megahit` ended non-zero before fresh artifact production
    - `Flye` produced real Docker and Cromwell-success artifacts, but the old
      completion judge still marked it incomplete
- Root-caused and fixed two harness-measurement problems revealed by that real
  train baseline:
  - fresh one-shot runs were being contaminated by historical generated
    artifacts in `.workspaces/oneshot/<repo>`, so the runner now clears prior
    Docker/WDL/Cromwell outputs before execution and quarantines permission-
    blocked stale directories as `*.stale.<timestamp>`
  - the completion judge was too narrow for real successful runs such as
    `Flye`, so it now accepts `docker_run.log` as a valid real-run log and
    accepts a fresh copied WDL under `results/wdl_file/` even when the repo
    root no longer contains the generated WDL
- This is useful thesis evidence because it distinguishes three different
  sources of harness failure that would otherwise be conflated:
  - true agent/runtime failures
  - stale-workspace contamination from previous experiments
  - evaluator false negatives caused by an incomplete completion rubric
- After the evaluator fix, the recorded `Flye` artifacts from that same run now
  recompute as a full completion, so the effective train picture is already at
  least `2/5` (`Flye`, `trinityrnaseq`) before the next clean rerun.
- Completed the next clean rerun cycle and obtained the first full 8-repository
  real-task baseline split across train and holdout:
  - `train` rerun:
    `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T105103Z`
  - `holdout` rerun:
    `results/harness/benchmark_repo_harness/benchmark-repo-harness/20260422T105606Z`
  - measured outcomes:
    - train `3/5`: `spades`, `megahit`, `trinityrnaseq`
    - holdout `2/3`: `covid-19-signal`, `fieldbioinformatics`
    - combined `5/8`
- This rerun is useful thesis evidence because it shows the earlier freshness
  and evaluator fixes were not just local cleanup:
  - `spades` moved from an earlier remote/internal failure into a real full
    baseline pass once the fresh-run path became trustworthy
  - the system now has one stable positive baseline in each major repo cluster:
    assembly-heavy (`spades`, `megahit`, `trinityrnaseq`) and workflow/virus
    pipelines (`covid-19-signal`, `fieldbioinformatics`)
  - the remaining misses are now a narrower optimization target set rather than
    a vague “the harness is not working yet” problem
- The remaining baseline misses are themselves informative:
  - `canu` and `v-pipe` still end without fresh Docker/WDL artifacts, which
    points more toward early execution-path control/prompting than toward raw
    environment breakage
  - `Flye` still misses the rerun completion contract despite earlier direct
    evidence that it can be run successfully, which makes it a useful case for
    studying agent inconsistency and completion-judgment alignment under the
    same environment
- With `5/8` now established as the simple real-task harness baseline, the next
  thesis-relevant step is no longer “collect more baselines”, but “run the
  first small keep/discard optimization loop against the known miss set”.

### 2026-04-21

- Updated the repo-tracked local development gateway baseline to the current
  remote endpoint:
  - changed `.code2workspace/config.toml` from the loopback URL
    `http://127.0.0.1:8080/v1` to `http://8.221.123.105:8080/v1`
  - follow-up validation against the remote gateway showed the OpenAI-compatible
    API surface still lives under `/v1`, while the root path serves the HTML
    gateway page rather than API responses
  - kept `use_responses_api = false` unchanged so the working chat-completions
    compatibility baseline stays consistent
- Converted the ad hoc local benchmark assets into a more thesis-usable
  seven-case benchmark surface under `experiments/benchmark/`:
  - moved the benchmark datasets and `新冠病毒组装` case assets out of the old
    `experiments/oneshot/` location
  - normalized the benchmark catalog to those seven real local cases instead of
    the earlier eight-case draft that still mentioned `v-pipe`
  - rewired the benchmark helper to the new catalog location and fixed the
    image-tag resolution bug that could produce invalid references like
    `image:tag:latest`
- Replaced dead historical absolute input paths in the local benchmark WDL
  inputs with real repo-local dataset paths:
  - short-read cases now use the shared E. coli FASTQ pair already stored under
    `experiments/benchmark/datasets/downloads`
  - long-read cases share the verified PacBio input already used in the Canu
    real-test path
  - Trinity and covid-signal now use bundled local sample data
  - fieldbioinformatics now points at bundled test data plus explicitly managed
    Clair3 model files instead of the removed `deepagent` workspace
- Started a real seven-case local benchmark run under
  `results/skills/benchmark-workflow-orchestrator/20260421-covid-assembly-benchmark`
  and recorded layered completion evidence instead of treating the benchmark as
  all-or-nothing:
  - `spades`, `megahit`, and `trinityrnaseq` now have real WDL-success
    evidence in the new run root
  - `canu` has real repo-native success evidence and its WDL path was pushed
    into real execution
  - `Flye` repo-native execution reached deep real assembly stages with real
    intermediate outputs when last checked
  - `covid-19-signal` and `fieldbioinformatics` produced explicit blocker
    evidence rather than silent absence of results
- These outcomes are useful thesis material because they show three different
  benchmark-result classes inside one controlled run:
  - true positive executions with reusable artifacts
  - long-running in-progress scientific workflows that need more wall-clock
    budget but are clearly beyond setup failure
  - externally constrained failures with concrete evidence, such as
    network-dependent environment bootstrap and image/runtime command-surface
    mismatch
- Added a softer orchestration layer for skills rather than a hard external
  router:
  - the planning skill now emits a structured recommendation contract for
    benchmark, paper2workspace, and mixed multi-lane prompts
  - the CLI agent injects that recommendation into the model context as
    guidance, keeping the final execution decision with the agent itself
  - isolated benchmark/workspace copies may now keep project skills visible
    through a `.code2workspace/project-root.txt` pointer while still excluding
    historical results
- This is useful thesis evidence because it preserves the “skills shape agent
  behavior” design while addressing two concrete experimental failure modes:
  - project skills disappearing when fresh-run isolation hides the original
    repository root
  - long benchmark tasks finishing execution but failing to synthesize results
    because no report-first guidance was present in the orchestration layer
- Root-caused and fixed a web-layer concurrency issue revealed during live
  API validation:
  - submitting a quick one-shot task through the web API and polling its status
    at the frontend cadence could leave the run stranded in `running`
  - the same CLI command completed normally when run directly, which isolated
    the problem to the web store / polling interaction rather than the core
    agent runtime
  - enabling SQLite `WAL` mode plus a busy timeout in the web store restored
    successful completion under the real 1.5-second polling cadence
- Removed the checked-in browser frontend and static SPA assets from
  `apps/webapp` after the OpenHands-shell experiment:
  - the repository now keeps only the lightweight web API/backend pieces
  - this narrows the repo back toward runtime, experiment, and harness work
    rather than ongoing browser UX development
- Repaired a concrete interactive terminal regression in the current CLI:
  - the TUI was no longer advancing past `Connecting to local server...`
    even though the local LangGraph server had already become healthy
  - root cause was not server startup failure, but stale Textual message
    handler names left behind after the app class rename to
    `Code2WorkspaceApp`
  - after aligning the handler names with the class name, the TUI again
    reaches the normal ready prompt
- This is useful thesis evidence because it distinguishes two different failure
  classes in agent tooling:
  - execution-path failures caused by model/tool/runtime behavior
  - UI orchestration failures caused by event wiring after architectural
    refactors
- Regression coverage was added for both direct handler execution and actual
  `post_message(...)` dispatch of startup events, which improves confidence that
  future CLI/TUI renames will not silently strand the interface in a
  pre-session state
- Adjusted the normal CLI session model so that new sessions now default to a
  timestamped per-session working directory under `workspace/` in the user
  invocation directory:
  - this makes ordinary interactive and non-interactive runs easier to isolate
    from one another
  - existing fixed-layout experiment runners explicitly opt out and preserve
    their original repository working directories so historical experiment
    layouts remain comparable

### 2026-04-19

- Searched the current server for previously saved thesis-style reference
  materials:
  - an actual local reference folder was later found under
    `/home/zhangpf/参考模版（注意内容无关）`
  - it contains prior `开题报告` / `任务书` / `毕业论文` samples, which are useful
    for structural imitation even though the content domain is unrelated
- Continued the thesis-writing track instead of feature work and tightened the
  Chinese harness chapter into a more dissertation-like structure:
  - added a clearer problem statement, formal method sections, experimental
    setup, result interpretation, and chapter summary
  - promoted the existing notes into directly reusable tables, including a
    repo-level one-shot result overview and a `spades` evolution timeline
  - added a harness-loop flow diagram so the outer-loop procedure is easier to
    explain in the final thesis
- Added two thesis-planning documents to reduce future writing ambiguity:
  - `experiments/harness/THESIS_OUTLINE_ZH.md` now defines a full-chapter thesis
    outline, recommended chapter ordering, and suggested figures/tables
  - `experiments/harness/THESIS_EXPERIMENT_DESIGN_ZH.md` now separates completed
    experiments from planned experiments and formalizes research questions,
    baselines, metrics, and pending validation items
- Revised the planning documents after reading the local reference samples:
  - the thesis outline now mirrors the observed undergraduate-thesis structure
    more closely: front matter, Chinese/English abstracts, chapter-style main
    body, conclusion, references, and acknowledgements
  - the experiment-design document now borrows the `开题报告` style of
    `研究主要内容` / `研究方案和思路` / `论文框架结构` / `工作进度安排`, while keeping
    completed and planned experiments clearly separated
- Materialized the plan into concrete thesis-writing artifacts:
  - added `experiments/harness/THESIS_FULL_DRAFT_ZH.md` as the first end-to-end
    manuscript draft with front matter, Chapters 1-5, conclusion, seed
    references, acknowledgements, and appendices
  - added `experiments/harness/THESIS_ASSET_MATRIX_ZH.md` to track every
    required figure/table, its chapter placement, source, and whether it is
    ready or still depends on future experiments
  - added `experiments/harness/THESIS_APPENDIX_TEMPLATES_ZH.md` so future
    experiment records, prompt-surface history, and completion-rubric evidence
    can be copied into appendices without re-designing the format
- Integrated `SWE-bench Lite` into the thesis-writing track as a planned
  external benchmark layer:
  - the thesis now uses a two-level evaluation narrative: `SWE-bench Lite` for
    general software-engineering ability, and the existing bioinformatics
    repository tasks for domain-specific execution ability
  - corresponding placeholders were added to the manuscript,
    experiment-design document, outline, and figure/table asset matrix so later
    sessions can fill results without redesigning Chapter 5
- Tightened an important methodological nuance for later writing:
  - the repository code now contains evidence-backed completion judgment logic
    in `experiments/oneshot/completion.py`
  - however, some early run artifacts in `results/oneshot/` were generated
    before that schema had fully stabilized
  - the thesis should therefore distinguish between the final evaluation design
    and the exact metadata available in early baseline runs
- Consolidated the current evidence into a more defensible narrative:
  - the current one-shot evidence snapshot already shows three automatic
    end-to-end completions (`v-pipe`, `covid-19-signal`, `fieldbioinformatics`)
  - heavy repositories such as `spades`, `canu`, and `megahit` have reached
    real build execution but still expose reliability and budget limits
  - this strengthens the thesis claim that the central problem is harnessing and
    execution reliability rather than task impossibility

### 2026-04-16

- Established the repository as an actively maintained graduation-project base.
- Verified the current local OpenAI-compatible gateway setup for CLI execution.
- Added a tracked development log and repository-state handoff flow.
- Defined three concrete product directions:
  - minimal web workspace
  - generic one-shot repo-task runner
  - harness practice inspired by `better-harness`
- Started implementing a web-facing interaction layer and experiment
  scaffolding.
- Refined the implementation sequence into four phases:
  - usable web control plane
  - repeatable one-shot experiment entrypoint
  - explicit harness surfaces and repo splits
  - first expensive real baseline
- Recorded current engineering constraints that should appear in the thesis:
  - local gateway compatibility gaps with the Responses API path
  - temporary separation between browser session state and CLI/TUI runtime state
  - high runtime cost of bioinformatics repositories, which forces staged
    experimentation
- Completed the second-round prototype iteration:
  - the web control plane moved from single-latest-run view to basic session
    management
  - the one-shot runner gained machine-readable manifests and batch scheduling
  - the harness directory now contains concrete editable surfaces and repo
    splits rather than placeholders only
- Collected the first real baseline evidence from `spades`:
  - heavy scientific repositories can trap the current agent in a prolonged
    repository-understanding phase before any real build/test execution starts
  - the first baseline therefore produced useful failure evidence even without
    task completion
  - this directly motivated a prompt-surface change toward earlier minimal real
    execution
- Improved the experiment runner based on that baseline:
  - absolute CLI project path for real target-repo execution
  - incremental log flushing
  - explicit interrupted-run summaries
  - suppression of unrelated Tavily warnings in local development
- Isolated a critical system-level cause for failed scientific-workflow
  experiments:
  - non-interactive runs did not expose shell/execute tools unless shell access
    was explicitly enabled
  - this meant the agent could reason about Docker/WDL tasks but could not
    honestly perform them
  - enabling shell access changed the failure mode from capability absence to
    planning inefficiency before the first build
- Adjusted the experiment harness toward realistic long-running evaluation:
  - per-repository oneshot runs now default to a 30-minute timeout
  - timeout is treated as an explicit experiment outcome instead of an implicit
    manual interruption
- Continued the `spades` case study and refined the failure taxonomy:
  - longer timeout alone did not solve early-stop behavior
  - after another prompt iteration, the agent crossed into real Docker image
    construction
  - the next observed failure source came from external package-mirror
    instability rather than repository misunderstanding
- The `spades` baseline now supports a more rigorous thesis narrative:
  - failure mode 1: wrong runner path assumptions
  - failure mode 2: missing execution capability in the agent tool surface
  - failure mode 3: excessive pre-build convergence even after shell access is
    restored
  - failure mode 4: after the system-level blockers were removed, remaining
    failures became concrete task-interface mistakes that can be corrected with
    prompt or harness iteration
- The same `spades` case study now also provides a positive end-to-end success
  trace:
  - Docker image construction and container test can be reached on a heavy
    scientific repository
  - a WDL interface using the built image and repository-provided real test
    reads can be executed through Cromwell to `Succeeded`
  - this strengthens the thesis claim that the main obstacle is execution
    reliability and harnessing, not inherent impossibility of the repository
    task

### 2026-04-17

- The web control plane was intentionally simplified after the initial richer UI
  iteration:
  - the project now favors a stable, plain control-plane presentation over
    dynamic dashboard effects
  - this is relevant to the thesis because the browser layer is being treated as
    an operational console for experiments, not as an autonomous product surface
- The first post-`spades` batch over the remaining repositories yielded a
  clearer reliability taxonomy:
  - `canu` and `megahit` both entered real Docker build execution and then timed
    out under the 30-minute budget
  - this shows the system is no longer blocked at prompt generation or tool
    access on these repositories
  - the limiting factor for those runs is long-running build convergence, not
    absence of executable actions
- The batch then failed before finishing because `Flye` hit a transient
  `git clone` transport error:
  - this was a repository-preparation failure, not an agent reasoning failure
  - the batch runner currently treats that kind of failure too harshly and
    aborts the full queue instead of emitting a per-repository failure record
- This is useful thesis evidence because it sharpens the boundary between:
  - agent/task failures inside a prepared workspace
  - orchestration failures in the experiment harness itself
  - external infrastructure failures such as Git transport or package mirror
    instability
- The current next engineering step therefore follows directly from the
  evidence:
  - harden the oneshot batch entrypoint so setup failures are serialized as
    experiment outcomes
  - then continue the remaining repository baselines before moving from baseline
    collection into harness implementation
- That hardening step has now been implemented locally:
  - repository preparation failure is treated as an explicit per-repository
    result (`setup_failed`) at the single-run layer
  - unexpected per-repository exceptions are treated as explicit `batch_error`
    outcomes at the batch layer instead of aborting the queue silently
  - this improves the methodological quality of the experiment loop because
    partial failures remain analyzable rather than disappearing into one broken
    batch process

### 2026-04-18

- The first local harness loop now exists as a real research artifact rather
  than as a placeholder directory:
  - editable harness surfaces are materialized as explicit variants
  - each optimization iteration now has a proposer workspace, a candidate
    variant, split-level evaluation, and a serialized keep/discard decision
  - the current decision rule uses combined `train + holdout` pass count, which
    is simple but methodologically defensible for a prototype thesis system
- This matters for the thesis because the optimization object is now the harness
  configuration itself, not an untracked sequence of prompt edits:
  - the baseline and each candidate are persisted as named variants
  - the iteration history is recorded as machine-readable artifacts
  - the final report compares baseline and final variants in a reproducible way
- The completion label used by the one-shot runner was also upgraded from a weak
  keyword check to an evidence-backed judgment:
  - completion now depends on fresh Docker/WDL artifacts, real command logs,
    Cromwell success evidence, and explicit final completion declaration
  - this reduces false positives from stale outputs or purely verbal claims of
    success
  - the resulting `completion_judgment` block strengthens the validity of the
    evaluation protocol and is directly useful for the thesis methodology
    chapter
- A thesis-oriented method draft has been added under
  `experiments/harness/THESIS_METHOD.md`:
  - it frames the system as surface-based harness optimization
  - it compares the method against direct one-shot execution and manual prompt
    iteration
  - it states the architectural value of split-based evaluation and
    evidence-backed completion judgment in research terms
- A Chinese thesis-style chapter draft has also been added under
  `experiments/harness/THESIS_CHAPTER_ZH.md`:
  - it rewrites the harness method in dissertation-style prose
  - it adds a baseline comparison table
  - it consolidates the `spades` case study into a reusable experimental
    narrative with concrete timestamps and workflow evidence

### 2026-04-19

- The repository-baseline material for the second one-shot batch has now been
  consolidated into per-repository notes:
  - `canu`, `megahit`, and `v-pipe` each have explicit baseline notes under
    `results/oneshot/<repo>/BASELINE_NOTES.md`
  - this matters for thesis traceability because follow-up sessions no longer
    need to reconstruct the evidence chain from raw logs alone
- The heavy-repository timeout taxonomy is now sharper than the earlier generic
  label of "timed out":
  - `canu` and `megahit` both found real repository-native validation paths and
    entered real Docker build execution
  - in both cases, the 30-minute budget was primarily consumed by first-build
    environment setup, especially Ubuntu package installation, before repository
    compilation or WDL validation began
  - this is a different failure mode from prompt drift, missing shell
    capability, or inability to identify test data
- `v-pipe` now serves as an additional positive end-to-end control case beyond
  `spades`:
  - the one-shot run built the image, executed a real HIV test layout from the
    repository, and completed a WDL workflow through Cromwell with status
    `Succeeded`
  - the direct container output and the WDL output for `ref_majority.fasta`
    match by SHA256, which strengthens the evidence-backed completion story
- This changes the immediate methodological implication for the thesis:
  - future optimization for `canu` and `megahit` should focus first on
    build-budget policy, workspace/layer reuse, or prebuilt dependency layers
  - it is now less defensible to treat every timeout on a heavy scientific
    repository as a planning failure by the agent

## Writing Reminders

- Record why a design was chosen, not only what changed.
- Keep evidence of failed compatibility paths, because it strengthens the
  evaluation section of the thesis.
- When running repo experiments, save prompts, logs, outputs, and final
  judgments in reusable form.
