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

### 2026-04-21

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
