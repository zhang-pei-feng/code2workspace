---
name: benchmark-workflow-orchestrator
description: Orchestrate Bio-OS workflow reuse, batch benchmark execution, result collection, and benchmark summarization for requests about workflow comparison, benchmark runs, multi-workflow reuse, Bio-OS submissions, template filling, and result download. Use when the user asks to compare multiple workflows, benchmark assembly tools, reuse existing workflows on the same input, or obtain benchmark summaries without calling legacy ACP or DeepAgents agents.
---

# Benchmark Workflow Orchestrator

Use this skill when the user wants a benchmark or multi-workflow reuse flow,
especially in Bio-OS-oriented tasks.

## Always do

1. Work entirely inside the current `code2workspace` repository.
2. Never call old runtime entrypoints under `/mnt/data1/zhangpf/superagent/...`.
3. Prefer the project subagent `bioos-operator` for Bio-OS-heavy branches.
4. Save outputs under `results/skills/benchmark-workflow-orchestrator/...`.

## Entry points

- Shared helper probe:
  `python3 skills/_shared-superagent-helpers/scripts/bioos_ops.py probe`
- Shared workspace listing:
  `python3 skills/_shared-superagent-helpers/scripts/bioos_ops.py list-workspaces`
- Skill front-door:
  `python3 skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py --help`

## Workflow

1. If the user asks for benchmarking, workflow comparison, or reusing multiple
   workflows on the same input, first inspect Bio-OS readiness with the shared
   `probe` command.
2. If the environment is ready, delegate Bio-OS execution details to
   `bioos-operator`.
3. If the environment is not ready, do not fake execution. Produce a structured
   plan/result stub and clearly say what is missing.
4. For local summary-only tasks, run
   `python3 skills/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py summarize ...`
5. When the result directory already exists, summarize real result files instead
   of inventing benchmark metrics.

## Output rules

- Mention the output directory first.
- If the run is only partially executable, state exactly which prerequisites are
  missing.
- If real Bio-OS execution happened, surface real workspace / workflow /
  submission identifiers only.
- Never claim benchmark completion without real artifact paths.
