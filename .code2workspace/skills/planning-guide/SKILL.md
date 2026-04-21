---
name: planning-guide
description: Improve planning for complex, multi-step, multi-source, ambiguous, investigation-heavy, research-heavy, or verification-heavy tasks. Use this skill when the agent should pause before acting, clarify success criteria, separate locally discoverable facts from external evidence needs, choose information sources deliberately, and define a verification path before implementation or reporting.
---

# Planning Guide

Use this skill when the task is large enough or uncertain enough that acting
immediately is likely to waste time.

This is the unified planning skill for the project. The old
`planning-orchestrator` name is now only a compatibility wrapper around the
same generic planning flow.

Typical cases:

- multiple steps or dependencies
- multiple possible information sources
- unclear success criteria or constraints
- research, monitoring, reporting, debugging, or investigation work
- tasks where the wrong first step is expensive

## What this skill does

- reminds you to plan before committing to execution
- helps you separate local facts from external evidence gaps
- helps you choose evidence sources by task shape
- helps you define a verification path before implementation or conclusions
- can materialize a generic local planning contract when you want a reusable
  plan artifact instead of ad hoc reasoning

## What this skill does not do

This skill does not force downstream execution or mandatory dispatch. It may
emit a soft skill recommendation when the task shape is obvious, but the agent
still decides whether to follow that recommendation.

## Compact Workflow

1. Clarify the goal and success criteria.
2. Identify constraints, blockers, and missing information.
3. Separate facts you can discover locally from facts that require external
   evidence.
4. Choose the cheapest authoritative sources before execution.
5. Define how you will verify the result before you start implementing or
   answering.

## References

- For source-selection heuristics, read `references/source-selection.md`.
- For a reusable planning checklist, read `references/checklist.md`.
- For short planning examples by task shape, read `references/case-index.md`.

Read the principles first, then pick the closest case when you want a compact
planning pattern instead of inventing the structure from scratch.

## Optional Local Plan Contract

If you want a reusable local plan artifact, use:

- `python3 skills/planning-guide/scripts/planning_tool.py classify --task "<task>"`
- `python3 skills/planning-guide/scripts/planning_tool.py init --task "<task>"`
- `python3 skills/planning-guide/scripts/planning_tool.py dispatch --run-dir "<run-dir>"`
- `python3 skills/planning-guide/scripts/planning_tool.py status --run-dir "<run-dir>"`

The generated plan stays soft-routing only:

- may recommend a relevant orchestrator skill
- may suggest multi-lane decomposition for mixed tasks
- no automatic downstream execution
