# Multi-Source Report Parallel Subagent Budget Design

## Summary

Upgrade `multi-source-report` so it behaves more like the
`deepagents/examples/deep_research` pattern:

- one orchestrator
- one reusable report-research subagent type
- multiple parallel subagent instances for different lanes
- fixed, explicit research-depth controls stored in the report run metadata

The goal is to reduce the current "over-explore before writing" behavior and
force the agent into a tighter loop:

1. init report run
2. split into 2-3 lanes
3. launch parallel `report-researcher` tasks
4. collect lane notes
5. synthesize
6. compose final report

This design intentionally makes the research-depth controls **fixed defaults**
for now, not dynamic by task complexity.

## Required Behavior

### Parallel-subagent model

`multi-source-report` should adopt the same high-level execution pattern used by
the `deep_research` example:

- the main agent is the orchestrator
- `report-researcher` is the only default evidence-gathering subagent type
- the orchestrator should launch multiple `report-researcher` tasks in a single
  response when lanes are independent
- `report-synthesizer` remains available, but should be optional rather than
  the primary source of structure

This means the system should prefer:

- 2-3 parallel `report-researcher` lanes for formal reports
- one bounded lane per evidence aspect
- one final synthesis/composition stage

It should avoid:

- long repository/tool exploration before starting lane work
- self-directed serial research by the main agent when lane decomposition is
  already obvious
- open-ended evidence gathering after the minimum lane set is already covered

### Fixed research-depth defaults

The first version should not vary by "simple" vs "complex" tasks.

Use fixed defaults for all formal `multi-source-report` runs:

- `max_concurrent_research_units = 3`
- `max_researcher_iterations = 6`

These values should be stored in `manifest.json` and available to both the main
orchestrator logic and the subagent instructions.

The user may override them later, but the default path must be stable and
explicit.

### Why these defaults

- `3` parallel lanes is conservative and already matches the structure used in
  the `deep_research` reference
- `6` research iterations is deeper than the original reference's `3`, which is
  useful for report tasks that need multi-source evidence, but still bounded
  enough to stop infinite exploration

## Interface Changes

### `report_tool.py init`

Add explicit init-time parameters:

- `--max-concurrent-research-units`
- `--max-researcher-iterations`

If omitted, write these defaults into `manifest.json`:

- `max_concurrent_research_units = 3`
- `max_researcher_iterations = 6`

The run manifest should become the single source of truth for these values.

### Manifest additions

Each new `multi-source-report` run should persist:

- `max_concurrent_research_units`
- `max_researcher_iterations`

These should sit alongside existing report controls such as:

- `report_mode`
- `min_report_chars`
- `prefer_tables`
- `max_tables`

## Prompt / Agent Contract Changes

### Orchestrator prompt changes

Port the useful deepagents prompt behavior into `multi-source-report`:

- create todos first
- initialize the report directory early
- delegate research with `task()` rather than doing all research locally
- issue multiple `task()` calls in the same response when lanes are independent
- stop broad research once lane coverage is sufficient
- move to synthesis/composition as soon as the minimum evidence threshold is met

Add explicit orchestration rules:

- after reading the request and initializing the run directory, the orchestrator
  should not spend many steps reading repository files unless they are directly
  needed for evidence gathering
- the orchestrator should prefer starting lane work over inspecting tool
  internals
- if the task clearly maps to standard lanes, the orchestrator should launch the
  lanes immediately

### `report-researcher` prompt changes

Adapt the deepagents `RESEARCHER_INSTRUCTIONS` to this repo's local-skill
environment:

- each `report-researcher` handles one bounded lane only
- the lane may use project skills first, then `fetch_url` / `web_search` as
  augmentation
- the lane should track its own research rounds
- the lane must stop at `max_researcher_iterations`
- the lane should stop earlier if it already has enough evidence
- if two consecutive rounds do not materially improve the lane, it should stop
  and return a lane note

### `report-synthesizer` role

Keep `report-synthesizer`, but treat it as:

- optional for large or high-value report tasks
- useful when the lane notes need an extra synthesis pass
- not required before `compose`

The default critical path should remain:

- lane research first
- compose as soon as minimum evidence exists

## Execution Rules

### Default lane count

For formal reports, the orchestrator should target 2-3 evidence lanes by
default, not 4-5 unless the prompt truly requires it.

Recommended default decomposition:

- lane 1: monitoring / official signals
- lane 2: source provenance or local structured evidence
- lane 3: literature / technical or risk-specific evidence

This keeps the first iteration cheap enough to finish while still allowing
multi-source coverage.

### Compose threshold

The orchestrator should move to composition when:

- at least 2 evidence lanes are completed for general reports
- at least 3 evidence lanes are completed for risk-oriented reports
- remaining missing lanes are either explicitly non-critical or evidence-poor

It should not continue researching indefinitely just because more sources
exist.

## Test Plan

### Tool-level tests

Add tests that `init` writes:

- `max_concurrent_research_units = 3`
- `max_researcher_iterations = 6`

Add tests that explicit overrides are preserved in the manifest.

### Behavior / contract tests

Update or add live-eval-style cases that verify:

- the report behavior prompt triggers multiple `task()` invocations
- parallel lane work uses `report-researcher`
- the final answer no longer stops at "still gathering evidence" when lane
  coverage is already sufficient

### Regression focus

The success criterion for the next real prompt validation is not just "some log
exists". It should be:

- the report reaches final composition
- `final_report.md` exists
- the final user-visible answer contains report body content rather than only
  planning/progress text

## Scope Boundaries

Included:

- fixed research-depth controls in the manifest
- parallel lane orchestration defaults
- prompt tightening toward earlier composition
- tests for new manifest defaults and behavior expectations

Excluded:

- changing model provider/model selection
- introducing multiple new lane-specific report subagent types
- adding a chart/image generation pipeline
- dynamic complexity-based budgeting in this version

## Defaults Chosen

- Use one evidence-gathering subagent type: `report-researcher`
- Keep `report-synthesizer` optional
- Fixed defaults:
  - `max_concurrent_research_units = 3`
  - `max_researcher_iterations = 6`
- Prefer 2-3 evidence lanes by default
- Optimize for finishing a report within budget rather than maximizing evidence
  breadth in one run
