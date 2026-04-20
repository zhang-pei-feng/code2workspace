# Harness Method Draft

This document is a thesis-oriented method draft for the local
`code2workspace` harness system.

It is written as reusable technical prose rather than as repository notes only.
The intended use is to adapt it into the "Method", "System Design", or
"Experimental Framework" chapter of the undergraduate thesis.

## 1. Problem Setting

The target task in this project is not a short benchmark-style coding problem.
Instead, the agent is asked to transform a real scientific software repository
into a runnable workspace and to complete a multi-stage execution task that
includes:

- repository inspection
- Docker image construction
- containerized real-data validation
- WDL interface authoring
- Cromwell-based workflow execution

This task family is expensive, stateful, and highly sensitive to harness
behavior. Small prompt or policy changes can materially alter whether the agent:

- enters real execution early enough
- records real outputs instead of partial preparation artifacts
- reaches an actual success state rather than a plausible-looking but invalid
  endpoint

The central research problem is therefore:

How can one optimize an agent harness for long-running repository tasks in a way
that is reproducible, auditable, and resistant to overfitting?

## 2. Baseline Approaches and Their Limitations

Two practical baselines motivated the current harness design.

### 2.1 Baseline A: Direct One-Shot Execution

In the simplest setting, a repository URL is mapped to a single prompt and the
agent is run once. Success or failure is then read from the final output or from
the investigator's manual inspection.

This baseline is operationally simple but methodologically weak:

- prompt changes are implicit and hard to version
- repeated runs are difficult to compare fairly
- completion labels are vulnerable to superficial keyword matches
- failures from repository setup, harness design, and agent reasoning are mixed
  together

### 2.2 Baseline B: Manual Prompt Iteration

A stronger informal baseline is to repeatedly edit the prompt after observing
failures. This is common in practice, but it still has major weaknesses:

- there is no explicit definition of what part of the harness changed
- there is no train/holdout split to control overfitting
- intermediate decisions are rarely serialized
- the final configuration is usually recoverable only from human memory or chat
  history

These limitations make the baseline difficult to defend in a thesis because the
improvement process is not itself a controlled experimental object.

## 3. Proposed Method: Surface-Based Harness Optimization

The proposed system reframes harness optimization as iterative search over a
small set of explicit, editable surfaces rather than as unconstrained prompt
tinkering.

### 3.1 Core Idea

Instead of treating each run as an isolated attempt, the system treats each run
as the evaluation of a concrete harness variant.

A variant is defined by the values of a set of named surfaces, such as:

- `one_shot_prompt`
- `completion_rubric`
- future planner or execution-policy surfaces

Each variant is materialized, executed, evaluated on explicit repository cases,
and then either kept or discarded.

This converts harness engineering from an ad hoc workflow into a structured
outer-loop optimization problem.

## 4. System Architecture

The implemented system has six main layers.

### 4.1 Inner Execution Layer

The inner layer is the existing one-shot repository runner under
`experiments/oneshot/`.

Its responsibilities are:

- clone or reuse the target repository
- derive a repository-specific task prompt
- launch `code2workspace`
- persist prompt, logs, manifests, and summary artifacts

This layer is the execution target being optimized, not the optimizer itself.

### 4.2 Surface Layer

The harness exposes editable components as named surfaces.

A surface is a real artifact loaded by the inner runner during evaluation.
Current live surfaces are:

- `one_shot_prompt`
- `completion_rubric`

The surface abstraction provides two methodological benefits:

- it makes the optimization object explicit
- it constrains the search space to semantically meaningful harness components

### 4.3 Variant Materialization Layer

For each experiment run, the system materializes a variant object that records:

- its label
- which surfaces differ from baseline
- the concrete value of every surface

During evaluation, workspace-file surfaces are patched into the repository and
then restored after the run.

This means the system never relies on a vague statement such as "the prompt was
improved". It always evaluates a concrete, serializable harness state.

### 4.4 Evidence-Backed Completion Judgment

One of the most important improvements over the initial baseline is the
replacement of keyword-based success checking with evidence-backed completion
judgment.

The current one-shot system now evaluates completion using a structured evidence
block called `completion_judgment`. This block checks, among other items:

- whether the repository-specific Dockerfile was freshly written
- whether a matching Docker image was actually built
- whether `results/docker_test` contains fresh non-log output artifacts
- whether the repository-specific WDL file was freshly written
- whether Cromwell was actually run
- whether a `Succeeded` workflow status is supported by logs or metadata
- whether `results/wdl_result` and `results/wdl_file` contain fresh artifacts
- whether the final answer explicitly declares `COMPLETED`

The key methodological point is that completion is now inferred from multiple
independent evidence channels rather than from a single final-token match.

### 4.5 Outer Proposer Layer

The outer layer creates a proposer workspace for each optimization iteration.

The proposer workspace contains:

- the current editable surfaces under `current/`
- a surface manifest
- visible train failures
- copied train artifacts
- visible history from previous iterations
- a task description

The proposer can now be configured in two ways:

- a local `[proposer].command` for smoke tests and deterministic contract checks
- a native `[better_agent]` Deep Agents outer proposer for real optimization

In both modes, the proposer is allowed to edit only the files under `current/`
and to summarize the proposed change in `proposal.md`.

This design separates:

- the environment where failures are observed
- the environment where harness edits are proposed
- the environment where candidate variants are re-evaluated

This separation is also what keeps the architecture from becoming bloated. The
system does not introduce a second repository execution stack. It preserves the
existing one-shot runner as the inner execution path and adds only a narrow,
surface-editing outer loop around it.

### 4.6 Decision and Reporting Layer

Each candidate is evaluated on explicit `train` and `holdout` splits.

The current keep/discard rule is intentionally simple:

- accept the candidate only if its combined `train + holdout` pass count exceeds
  the current accepted variant

This rule is strong enough to enforce non-trivial improvement while still being
easy to explain and audit.

All decisions are serialized, including:

- variant files
- split results
- iteration decisions
- final run report

This produces a complete experimental trail rather than only a final score.

## 5. Optimization Procedure

The current harness loop can be described procedurally as follows.

1. Load the experiment configuration and baseline surfaces.
2. Materialize the baseline variant.
3. Evaluate the baseline on `train` and `holdout`.
4. Build a proposer workspace from the current accepted variant and visible
   train failures.
5. Run the proposer command to edit the allowed surfaces.
6. Materialize the edited surfaces as a candidate variant.
7. Evaluate the candidate on `train` and `holdout`.
8. Accept the candidate if the combined pass count improves; otherwise discard
   it.
9. Repeat until the iteration budget is exhausted or no new candidate is
   produced.
10. Write a final report comparing baseline and final variants.

This procedure is intentionally close to better-harness in spirit, but adapted
to the repository-to-workspace task setting and the existing `code2workspace`
one-shot execution path.

## 6. Why This Architecture Matters

The value of the proposed harness is best understood through direct comparison
with the earlier baselines.

### 6.1 Compared with Direct One-Shot Runs

Direct one-shot runs optimize a single attempt.

The proposed harness optimizes a reusable harness configuration.

This distinction matters because the thesis is not only trying to show that one
repository can be solved once. It is trying to show that success rate can be
improved systematically across a task family.

In plain language, the optimization target changes from "did one run happen to
work?" to "did this harness variant raise measured pass count under the same
split?"

### 6.2 Compared with Manual Prompt Iteration

Manual prompt iteration is flexible but weakly controlled.

The proposed harness introduces:

- explicit surfaces
- explicit variant files
- explicit train/holdout splits
- explicit keep/discard rules
- explicit run reports

As a result, the optimization process itself becomes a valid experimental object
that can be described, rerun, and critiqued.

This also makes failed edits useful. A rejected candidate is still evidence,
because it records that a concrete harness change did not improve measured
outcomes.

### 6.3 Compared with Keyword-Based Completion Labels

A naive completion rule such as "output contains `COMPLETED`" is vulnerable to
false positives and cannot distinguish:

- planning from execution
- partial artifact creation from valid workflow completion
- stale outputs from outputs created in the current run

The evidence-backed completion judgment improves internal validity because the
label is grounded in fresh, run-local execution evidence.

### 6.4 Compared with Single-Split Evaluation

If only visible examples are used, prompt edits can overfit to the currently
observed repositories.

The split-based harness mitigates this by forcing candidate acceptance to depend
on both visible `train` behavior and private `holdout` behavior. This is not a
perfect guarantee of generalization, but it is substantially stronger than
single-split prompt editing.

### 6.5 Practical Effect on This Project

For the `code2workspace` repository task setting, the architecture has three
direct practical effects.

First, it gives the project a measurable success-rate target. The outer loop is
useful only if it raises combined `train + holdout` pass count, so "better
prompting" is no longer a purely subjective claim.

Second, it reduces optimization waste. Because the outer loop edits only
explicit surfaces and keeps the inner one-shot runner unchanged, new prompt or
completion ideas can be tested without rebuilding the whole execution system.

Third, it improves thesis defensibility. The contribution is no longer just
that some heavy repositories occasionally progress further under shell-enabled
one-shot runs. The stronger contribution is that harness changes can be
proposed, evaluated, accepted, or rejected under a serialized and
evidence-backed procedure.

## 7. Research Contributions Claimed by This Prototype

In thesis language, the current prototype supports three concrete claims.

### Contribution 1

It defines a practical surface-based formulation of harness optimization for
repository-to-workspace agents.

### Contribution 2

It implements a reproducible outer-loop optimization mechanism consisting of:

- proposer workspace construction
- candidate materialization
- split-based evaluation
- keep/discard decisions
- serialized experiment reports

### Contribution 3

It introduces evidence-backed completion judgment for long-running software and
workflow tasks, replacing a weak keyword-only success heuristic.

## 8. Current Scope and Limitations

The system is already defensible as a research prototype, but it still has clear
limitations.

### 8.1 Proposer Backend

The system now supports both a local `[proposer].command` contract and a native
`[better_agent]` Deep Agents outer proposer.

The remaining limitation is not architectural absence, but evaluation scale:
the Deep Agents proposer path has been integrated and tested in-repo, but it
still needs more real optimization runs on the repository split to establish
how much pass-rate gain it produces in practice.

### 8.2 Evaluation Scale

The repository split is still small. This is acceptable for a prototype chapter,
but a thesis should state clearly that the current evaluation demonstrates
feasibility and methodological structure rather than broad statistical coverage.

### 8.3 Task Cost

The target repositories are computationally expensive. As a result, the harness
must support staged experimentation and cannot rely on massive hyperparameter
search. This constraint is a core motivation for the explicit surface design.

## 9. Suggested Thesis Framing

The system can be framed in the thesis as follows:

"This work does not treat prompt engineering as an informal artisanal process.
Instead, it formalizes agent-harness optimization as iterative search over a
small number of explicit, versioned surfaces, with candidate selection governed
by split-based evaluation and evidence-backed completion judgment."

That sentence captures the methodological shift from baseline prompting to
research-grade harness optimization.

## 10. Implementation Mapping

For implementation traceability, the main components map to the repository as
follows.

- one-shot execution:
  `experiments/oneshot/run_repo_task.py`
- completion judgment:
  `experiments/oneshot/completion.py`
- harness core model and report layout:
  `experiments/harness/code2workspace_harness/core.py`
- proposer workspace and candidate materialization:
  `experiments/harness/code2workspace_harness/agent.py`
- baseline and optimization loop:
  `experiments/harness/code2workspace_harness/runner.py`
- editable surfaces:
  `experiments/harness/surfaces/`

## 11. Next Step for the Thesis

The next technical step is to run the integrated Deep Agents proposer on a
larger repository split and quantify how much combined `train + holdout`
improvement it can consistently recover. The next writing step is to pair this
method chapter with:

- one detailed `spades` case study
- one failure-taxonomy subsection
- one baseline-vs-harness comparison table

That combination would already form a credible undergraduate thesis evaluation
chapter.
