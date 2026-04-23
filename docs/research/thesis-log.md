# Thesis Log

This file records repository evolution as thesis material.

For the engineering-facing current snapshot, read
`docs/overview/current-status.md`. For thesis drafts and chapter assets, start
from `docs/research/README.md`.

## Working Thesis Direction

Design and implementation of a LangGraph-based agent system that converts
software repositories into runnable workspaces and executes structured software
engineering and scientific-workflow tasks with improved success rate through
harness-style iteration.

## Research Themes

- agent-oriented workspace interaction
- one-shot execution for long-running repository tasks
- reproducible experiment logging
- harness engineering for success-rate improvement
- frontend and runtime integration for controllable agent workflows

## Chronology

### 2026-04-22

- Added a thesis-facing asset-note generator so the already checked-in result
  bundles can be turned directly into caption-ready table notes:
  - new script: `experiments/harness/generate_thesis_asset_notes.py`
  - new tests: `experiments/harness/tests/test_thesis_asset_notes.py`
  - generated bundle: `results/thesis-asset-notes-20260422/`
  - current note coverage: table 5-2 historical one-shot baseline, figure 5-1
    baseline status chart, figure 5-2 failure distribution chart, table 5-8
    project-skill orchestration, table 5-9 reduced two-hour evaluation, and
    table 5-10 benchmark snapshot
- Added a dedicated summary bundle for the historical standard one-shot
  baselines used in thesis table 5-2:
  - new script: `experiments/harness/summarize_oneshot_baseline.py`
  - new tests: `experiments/harness/tests/test_oneshot_baseline_summary.py`
  - generated bundle: `results/oneshot-baseline-summary-20260422/`
  - `rows.csv` now also carries `completion_level` and `failure_category`, so
    figures 5-1 and 5-2 no longer need manual value extraction
  - this removes another manual table-transcription step from the current
    thesis-writing path
- Added a small figure-data exporter for the ready one-shot figures:
  - new script: `experiments/harness/generate_thesis_plot_data.py`
  - new tests: `experiments/harness/tests/test_thesis_plot_data.py`
  - generated bundle: `results/thesis-plot-data-20260422/`
  - the bundle directly provides `figure_5_1_counts.csv` and
    `figure_5_2_counts.csv` so the user can draw those two figures without any
    extra counting step
- Added a one-command thesis asset regeneration entrypoint:
  - new script: `experiments/harness/regenerate_thesis_assets.py`
  - new tests: `experiments/harness/tests/test_regenerate_thesis_assets.py`
  - this entrypoint sequentially regenerates the current project-skill,
    benchmark, two-hour, one-shot, plot-data, and asset-note bundles
- Tightened the thesis narrative so historical one-shot positives are no longer
  conflated with the newer reduced-eval / benchmark blocker evidence:
  - `THESIS_FULL_DRAFT_ZH.md`, `THESIS_CHAPTER_ZH.md`, and
    `THESIS_EXPERIMENT_DESIGN_ZH.md` now explicitly distinguish
    “historical standard one-shot baseline” from the current strongest
    completed samples (`spades`, `megahit`)
  - `THESIS_ASSET_MATRIX_ZH.md` now aligns table names and sources with the
    current chapter structure, including the soft-routing table and the
    benchmark snapshot wording
  - `docs/overview/current-status.md` now describes the benchmark line as an
    eight-tool snapshot built from seven checked-in local cases plus reused
    `v-pipe` evidence, which matches the checked-in summary bundle
- Added a stable observability layer for planner-driven orchestration in
  non-interactive runs:
  - quiet-mode CLI logs now print a deterministic `Planner:` summary plus a
    `Planner Contract:` line when `planning-guide` emits a recommendation
  - this turns soft routing from an internal middleware effect into a directly
    testable experimental signal
- Upgraded the checked-in harness config from a two-case demo to the live
  `train/holdout` repository split and attached fixed `stratum`
  labels to every case:
  - `spades` -> `phase-gate`
  - `canu` / `megahit` -> `dependency-convergence`
  - `Flye` / `trinityrnaseq` -> `long-run`
  - `v-pipe` -> `positive-control`
  - `covid-19-signal` -> `network-blocker`
  - `fieldbioinformatics` -> `runtime-surface`
- Added a low-cost project-skill orchestration evaluation lane under
  `experiments/skill_tests/` with four initial cases:
  - benchmark soft routing and fresh-run / shared-dataset constraints
  - paper2workspace routing and strict phase gate
  - mixed benchmark + workspace lane decomposition
  - paper2workspace phase-gated helper report generation
- Recorded initial real smoke evidence:
  - the unified 4-case batch passed under
    `results/skill-tests/project-skill-orchestration/20260422`
  - the batch covers benchmark routing, paper2workspace routing, mixed-task
    routing, and phase-gated workspace-report helper generation
- Extended the harness from a two-surface prompt/rubric prototype into a
  five-surface configuration:
  - `one_shot_prompt`
  - `completion_rubric`
  - `planning_guide_skill`
  - `benchmark_report_policy`
  - `paper2workspace_phase_gate`
- Added a deterministic `stratum_surface_proposer.py` smoke path and verified
  in tests that a real proposer iteration can accept a candidate by editing
  phase-gate / report-policy surfaces based on visible `stratum` labels.
- Ran the checked-in deterministic smoke optimize path end to end:
  - command:
    `PYTHONPATH=. uv run --project libs/cli python experiments/harness/run_stratum_smoke.py`
  - result root:
    `results/harness-smoke/stratum-surface-smoke/20260422T003336Z`
  - accepted candidate:
    `iter-001`
  - changed surfaces:
    `benchmark_report_policy`, `paper2workspace_phase_gate`,
    `planning_guide_skill`
  - combined delta:
    `+2` (`0/2 -> 2/2`)
- Added a more realistic local-repo smoke optimize path:
  - command:
    `PYTHONPATH=. uv run --project libs/cli python experiments/harness/run_local_repo_stratum_smoke.py`
  - result root:
    `results/harness-local-repo-smoke-fixture/runs/local-repo-stratum-smoke/20260422T020117Z`
  - this path materializes checked-in tiny repo fixtures and still goes through
    the real `run_repo_task()` clone / prompt / manifest / completion flow
  - accepted candidate:
    `iter-001`
  - combined delta:
    `+2` (`0/2 -> 2/2`)
- Started a reduced two-hour real-repository evaluation set to judge whether
  the harness is worth continuing for the current thesis task:
  - clean harness baseline on `spades` completed end to end with real Docker
    build, real container test, and real Cromwell `Succeeded` evidence under
    `results/harness-two-hour-eval/code2workspace-two-hour-eval/20260422T033624Z/.../spades/20260422T033624Z`
  - a later direct retry on `megahit` completed end to end with real Docker
    build, explicit-input container validation, and real Cromwell `Succeeded`
    evidence under `results/two-hour-spotcheck5/megahit/20260422T063109Z`
  - clean harness baseline on `megahit` failed fast due a model-side
    `APIError`, which is useful because it separates model service instability
    from repository/task blockers
  - direct spotcheck on `fieldbioinformatics` timed out only after real image
    build and a real container validation attempt that reproduced the `artic`
    PATH/runtime blocker
  - direct spotcheck on `v-pipe` timed out only after entering real Docker
    build plus Snakemake/conda environment creation
- This is useful thesis evidence because it already supports a practical
  methodological judgment: the current harness is good enough to push the agent
  into multiple real build/test/workflow completions and real blocker
  discovery, even
  before every repository in the reduced set fully settles.
- Wrote a thesis-facing summary memo for this reduced evaluation under
  `experiments/harness/TWO_HOUR_EVAL_20260422_ZH.md`, so the current “keep or
  stop using harness” judgment is no longer spread only across raw result
  directories.
- Added `experiments/harness/summarize_two_hour_eval.py` and generated
  `results/harness-two-hour-eval/summary-20260422/` so the reduced evaluation
  now also has one machine-readable / one markdown summary bundle instead of
  only scattered case-local `summary.json` files.
- Added `experiments/harness/summarize_project_skill_eval.py` and generated
  `results/project-skill-summary-20260422/`, so the project-skill
  orchestration lane now also has a plotting-friendly summary bundle.
- Promoted the `megahit` direct retry into a full `COMPLETED` case under
  `results/two-hour-spotcheck5/megahit/20260422T063109Z`, so the reduced
  evaluation now has two strong positive samples (`spades`, `megahit`) rather
  than only one.
- Added `experiments/harness/summarize_benchmark_snapshot.py` and generated
  `results/benchmark-summary-20260421/` from the checked-in benchmark report,
  so the benchmark line now also has a stable machine-readable / markdown
  summary bundle rather than only prose markdown.
- This is useful thesis evidence because it introduces a second experimental
  layer below expensive repo execution:
  - heavy repo-url tasks still measure real Docker/WDL/workflow execution
  - low-cost skill-orchestration cases now measure whether planner contracts,
    lane summaries, and phase-gate/report semantics are stable and observable

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
- Tightened the soft-routing contract into a more thesis-usable execution layer:
  - `planning-guide` now emits an explicit `execution_contract` with fresh-run,
    no-reuse, shared-dataset, no-interruption, phase-gate, and final-report
    expectations for benchmark / paper2workspace style tasks
  - mixed prompts now include lane dependencies plus a final synthesis lane
    rather than only a flat helper suggestion
  - `paper2workspace-orchestrator` now exposes structured `status` and `report`
    helper entrypoints so two-phase workspace runs can be summarized as real
    artifacts instead of ad hoc notes
- This matters for the thesis because it strengthens the methodological claim
  that success-rate improvements can come from externalized skills and planning
  contracts, not only from heavier changes to the core agent architecture.
- Extended the local harness case model with optional `stratum` labels and
  propagated them into split manifests plus proposer-visible train failure
  artifacts:
  - the harness can now preserve failure-mode tags such as cold-build,
    reporting, or phase-gate issues instead of only listing repository ids
  - this aligns the local outer loop more closely with the better-harness idea
    of optimizing against failure classes, not only against sample names
- This is useful thesis evidence because it supports a stronger future
  experimental claim: outer-loop improvements can be analyzed by failure mode
  and report completeness, not only by per-repo pass count.
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

### 2026-04-23

- Added a real `SWE-bench Lite` pilot line under `experiments/swebench/`:
  - new runner: `run_swebench_lite_pilot.py`
  - new summary helper: `summarize_swebench_lite.py`
  - default pilot subset: `pilot_instances.txt`
- Verified the official local harness path on this machine:
  - the first local `gold` control run failed because the default remote-image
    path hit Docker Hub unauthenticated pull rate limits (`429`)
  - forcing `--namespace none` switched the harness to local image builds and
    fixed that blocker
  - the follow-up local `gold` control on
    `marshmallow-code__marshmallow-1359` reached `resolved=1/1`
- Recorded the first non-gold `code2workspace` pilot result:
  - run root:
    `results/swebench-lite-pilot/runs/20260422T212019Z`
  - the agent produced a real patch plus a new regression test for
    `marshmallow-code__marshmallow-1359`
  - the first official evaluation attempt failed during instance-image build
    because container-internal `git clone` hit a transient HTTP2 framing error
  - a direct retry on the same `predictions.jsonl` succeeded and reached
    `resolved=1/1`
- Refreshed thesis-facing outputs so table 5-3 and figure 5-3 are now backed
  by real data:
  - summary bundle: `results/swebench-lite-summary-20260423/`
  - table CSV: `results/thesis-table-data-20260422/table_5_3.csv`
  - plot CSV: `results/thesis-plot-data-20260422/figure_5_3_counts.csv`
  - asset-note bundle now includes `table_5_3` and `figure_5_3`
- Expanded the pilot from a single-instance proof point to a 3-run dev-split
  mini-batch:
  - second run: `results/swebench-lite-pilot/runs/20260422T213823Z`
    (`pylint-dev__astroid-1268`)
    - the agent produced a real patch and ran targeted pytest successfully
    - official eval remained blocked after direct retry because the generated
      instance-image build repeatedly hit container-internal `git clone`
      HTTP2 framing errors
  - third run: `results/swebench-lite-pilot/runs/20260422T214632Z`
    (`pydicom__pydicom-1694`)
    - the agent produced a real patch plus a new regression test
    - official eval completed cleanly and reached `resolved=1/1`
  - the refreshed summary bundle now aggregates 3 real pilot runs with
    3/3 patch generation and 2/3 official resolved outcomes
- Hardened the pilot runner against official-eval flakiness:
  - `run_swebench_lite_pilot.py` now supports `official_eval_retries`,
    per-attempt evaluation logs, and `evaluation_attempts` metadata
  - the summary helper now deduplicates reruns by `instance_ids` and keeps the
    latest completed run for each pilot instance in the thesis-facing bundle
  - reran `pylint-dev__astroid-1268` under
    `results/swebench-lite-pilot/runs/20260423T025929Z`
    - the new run no longer fails in official eval due to transient Docker
      build/network issues
    - official harness now completes cleanly and judges the patch as
      `unresolved=1/1`
  - this changes the interpretation of the third pilot from
    “evaluation blocked by external network error” to
    “evaluation completed, but patch still did not resolve the benchmark task”
- Continued expanding and hardening the pilot set:
  - new resolved run:
    `results/swebench-lite-pilot/runs/20260423T030947Z`
    (`marshmallow-code__marshmallow-1343`)
    - the agent produced a real patch plus a regression test
    - official harness completed and reached `resolved=1/1`
  - added agent-side transient retry support to
    `run_swebench_lite_pilot.py`
    - new flag: `--agent-retries`
    - retry condition: empty patch plus transient model-side errors such as
      `InternalServerError` / `RemoteProtocolError`
    - per-instance output now records `agent_attempts`
  - new empty-patch/service-instability run:
    `results/swebench-lite-pilot/runs/20260423T033502Z`
    (`sqlfluff__sqlfluff-2419`)
    - two agent attempts both ended in `InternalServerError`
    - final official harness report is `empty_patch_instances=1`
  - the refreshed summary bundle now aggregates 5 unique pilot instances with
    4/5 patch generation, 3/5 official resolved, 1/5 official unresolved, and
    1/5 empty-patch service failure
- Reworked the thesis literature framing so it reads more like a software
  engineering agent paper than a repository diary:
  - chapter 1 now compares the project explicitly to `SWE-agent`,
    `AutoCodeRover`, `Agentless`, `OpenHands`, `Multi-SWE-bench`,
    `Saving SWE-Bench`, `SWE-EVO`, `Ambig-SWE`, and recent asynchronous
    software-engineering agent work
  - chapter 2 now includes a stronger comparison table that separates
    runtime-heavy, issue-resolving, benchmark-realism, and
    repository-to-workspace / harness-centric approaches
  - the reference list now carries those representative papers directly, so the
    thesis can be revised toward a more journal-like “related work +
    contribution positioning” style rather than staying as an engineering log

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

### 2026-04-22

- The thesis-facing asset pipeline now also covers the soft-routing /
  orchestration-comparison slot:
  - `experiments/harness/generate_thesis_asset_notes.py` now emits a seventh
    ready asset note for table 5-7 in addition to table 5-2, figure 5-1,
    figure 5-2, table 5-8, table 5-9, and table 5-10
  - `results/thesis-asset-notes-20260422/` was regenerated from the current
    checked-in summaries, so the soft-routing observability table now has a
    caption-ready interpretation grounded in real `Planner:` logs rather than
    in an invented "old router vs new router" comparison
- The thesis asset pipeline now also emits direct table CSVs:
  - `experiments/harness/generate_thesis_table_data.py` now generates
    `results/thesis-table-data-20260422/`
  - the bundle currently contains ready-to-format `table_5_2.csv`,
    `table_5_7.csv`, `table_5_8.csv`, `table_5_9.csv`, and `table_5_10.csv`
  - this reduces one more manual step between repository evidence and the final
    school-format manuscript
- The Chinese thesis drafts were tightened to align with those assets:
  - `THESIS_FULL_DRAFT_ZH.md`, `THESIS_CHAPTER_ZH.md`, and
    `THESIS_EXPERIMENT_DESIGN_ZH.md` now describe table 5-7 as a low-cost
    observability / regression layer backed by existing project-skill logs
  - stale mixed-English phrases such as "fresh completed", "runtime blocker",
    and "snapshot" were reduced or translated in the Chinese-facing sections
- An attempted subagent-assisted prose sweep failed for a platform-side reason
  unrelated to the repository:
  - the delegation path first returned transient `502 Bad Gateway` responses
    from `https://llm.yunhaoli.top/v1/responses`
  - a direct minimal retry then returned `403 Forbidden: This account only
    allows Codex official clients`
  - this is recorded as an environment/tooling limitation, not as a repository
    blocker or a thesis-system runtime regression
