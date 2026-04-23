# Harness Practice

This directory is reserved for `code2workspace`-specific harness experiments.

The reference design is:

- `/mnt/data1/zhangpf/deepagents/examples/better-harness`

## Why this exists

The repo needs a path from:

- ad hoc prompt debugging

to:

- structured baseline / candidate / holdout comparison

for the one-shot repo tasks.

## Current priority

The focus is now on harness implementation itself rather than continuing to
expand ad hoc baseline runs.

## Near-term plan

1. keep the current one-shot prompt and completion rubric as explicit surfaces
2. keep the imported OpenClaw skills available as reusable harness references
3. build a local baseline / proposer / keep-discard loop inspired by `better-harness`
4. connect the loop to the existing oneshot runner instead of inventing a second execution path
5. only return to large repo baselines when the harness can actually compare variants

## Candidate surfaces

- task prompt template
- completion rubric
- planner instructions
- shell validation policy
- result packaging instructions

## Placeholder structure

- `configs/`
- `cases/`
- `proposers/`
- `surfaces/`
- `runs/`
- `skills/`
- `code2workspace_harness/`

## Current concrete files

- `surfaces/one_shot_prompt.txt`
  - the current editable task prompt surface used by `experiments/oneshot/tasks.py`
- `surfaces/completion_rubric.txt`
  - the current baseline completion rule for deciding whether a run really finished
- `configs/repo_splits.toml`
  - the first train / holdout repository split
- `configs/baseline_layout.toml`
  - the current artifact contract between one-shot runs and future harness loops
- `configs/code2workspace_harness.toml`
  - the first local harness config for `validate`, `run-baseline`, and `optimize`
- `configs/benchmark_repo_harness.toml`
  - the first eight-repository real-task harness config driven by
    `configs/repo_splits.toml`
- `proposers/noop_proposer.py`
  - a no-op local proposer command for smoke-testing the proposer workspace contract
- `THESIS_METHOD.md`
  - thesis-oriented description of the harness method, baseline comparisons, and research value
- `THESIS_CHAPTER_ZH.md`
  - Chinese thesis-style draft with method narrative, baseline comparison table, and `spades` case study
- `skills/openclaw/`
  - imported OpenClaw skills and guides, trimmed to reusable skill content instead of local caches or tarballs
- `code2workspace_harness/`
  - the first local harness package modeled after `better-harness`
  - now includes config loading, surface patching, proposer workspace materialization, keep/discard decisions, run reports, CLI entrypoints, and the phase-1 benchmark-autonomy ladder

## Current commands

Validate the first harness config:

```bash
uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  validate experiments/harness/configs/code2workspace_harness.toml
```

Validate the eight-repository benchmark harness config:

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  validate experiments/harness/configs/benchmark_repo_harness.toml
```

Run the baseline surfaces through the current train/holdout split:

```bash
uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  run-baseline experiments/harness/configs/code2workspace_harness.toml
```

Run the real benchmark-repository baseline over the train split:

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  run-baseline experiments/harness/configs/benchmark_repo_harness.toml \
  --split train
```

Run the full keep/discard loop after wiring either a proposer command or a
`[better_agent]` deepagents config in the TOML:

```bash
uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  optimize experiments/harness/configs/code2workspace_harness.toml
```

Validate the phase-1 benchmark-autonomy ladder config:

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  validate-benchmark-autonomy experiments/harness/configs/benchmark_autonomy_phase1.toml
```

Run one or more phase-1 benchmark-autonomy combinations:

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/harness/code2workspace_harness/runner.py \
  run-benchmark-autonomy experiments/harness/configs/benchmark_autonomy_phase1.toml \
  --family short-read-assembly \
  --level level1
```

Import OpenClaw skills again if the source side changes:

```bash
uv run --project libs/cli python experiments/harness/import_openclaw_skills.py --clean
```

## Current run layout

- `variants/<variant>.json`
  - materialized surface values for baseline and candidate variants
- `history/visible/train/<variant>/`
  - visible train results for each evaluated variant
- `history/private/holdout/<variant>/`
  - holdout results used for keep/discard decisions
- `history/visible/iterations/<n>/proposer_workspace/`
  - the editable proposer workspace for that iteration
- `report.json` and `report.md`
  - final baseline vs final split summary plus iteration history

## Current boundary

The outer loop now supports two proposer modes:

- `[proposer].command`
  - legacy local script contract for smoke-testing and deterministic local
    automation
- `[better_agent]`
  - native deepagents outer proposer that edits the proposer workspace directly
    through a `deepagents` runtime

The preferred path is `[better_agent]`, but the command mode remains useful for
tests and offline contract checks.

## Real Benchmark Task Split

The current real-task harness split uses the eight target repositories already
tracked under `experiments/oneshot/targets.txt`.

- `train`
  - `spades`
  - `canu`
  - `megahit`
  - `Flye`
  - `trinityrnaseq`
- `holdout` (validation)
  - `v-pipe`
  - `covid-19-signal`
  - `fieldbioinformatics`

The reasoning is intentionally simple:

- keep the five assembly-heavy repositories in train because they are closest
  to the original Docker+WDL task surface
- reserve the three workflow/virus-pipeline repositories for validation so the
  harness has a harder out-of-sample check

## Why This Is Not Bloated

This architecture adds one outer optimization loop, not a second execution
stack.

- The inner repo-task path is still the existing one-shot runner.
- The outer layer edits only explicit harness surfaces such as the prompt or
  completion rubric.
- Success is still measured by the same repository runs, just now with
  train/holdout bookkeeping and keep/discard decisions around them.

In practical terms, this means the system is trying to improve success rate
without hiding the baseline under a rewrite. If a candidate improves combined
`train + holdout` passes, that gain is attributable to the changed surfaces. If
it does not improve passes, the run still leaves behind a concrete rejected
candidate and a trace of why it was not kept.

At this point both `one_shot_prompt` and `completion_rubric` are live surfaces:
the prompt surface is consumed by `experiments/oneshot/tasks.py`, and the
completion surface is consumed by `experiments/oneshot/completion.py` to produce
an evidence-backed `completion_judgment` in each one-shot run summary.
