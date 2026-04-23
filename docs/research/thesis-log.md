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
