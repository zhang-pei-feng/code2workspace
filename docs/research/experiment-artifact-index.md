# Experiment Artifact Index

This document is a checked-in index for experiment artifacts that live mostly
outside normal Git history as large local result directories.

Its purpose is to let other branches or the eventual main branch know:

- which local experiment runs are currently thesis-relevant
- which runs are exploratory and should not be merged into headline counts
- which summary assets are already regenerated inside the repo
- how to rebuild thesis-facing assets from the local raw runs

Large raw artifacts should remain local. This file is the lightweight handoff.

## Scope

- Machine-local worktree for this branch:
  - `/home/zhangpf/.paseo/worktrees/2ztjm8aa/fast-parrot`
- Repository-relative results root:
  - `results/`
- Current branch:
  - `add-openai-api-key`

## Main Rule

Treat this document as the source of truth for:

- which experiment runs are selected into thesis-facing summaries
- which experiment runs are useful discussion evidence only

Do not infer headline counts from every directory under `results/`; use the
selected-run lists below.

## Thesis-Facing Stable Summary Assets

These are small regenerated assets that are safe to keep using after branch
merge and are appropriate to push to the main code branch.

### SWE-bench Lite

- Aggregated summary:
  - `results/swebench-lite-summary-20260423/summary.json`
- Table asset:
  - `results/thesis-table-data-20260422/table_5_3.csv`
- Plot asset:
  - `results/thesis-plot-data-20260422/figure_5_3_counts.csv`
- Caption/note asset:
  - `results/thesis-asset-notes-20260422/SUMMARY_ZH.md`

Current stable selected headline set:

- `resolved`
  - `marshmallow-code__marshmallow-1359`
  - `marshmallow-code__marshmallow-1343`
  - `pydicom__pydicom-1694`
- `unresolved`
  - `pylint-dev__astroid-1268`
- `empty-patch`
  - `sqlfluff__sqlfluff-2419`

Current stable selected headline counts:

- unique pilot instances: `5`
- patch generated: `4`
- official resolved: `3`
- official unresolved: `1`
- empty patch: `1`

### Other Thesis-Facing Summaries

- Project-skill orchestration:
  - `results/project-skill-summary-20260422/summary.json`
- Benchmark snapshot:
  - `results/benchmark-summary-20260421/summary.json`
- Two-hour reduced evaluation:
  - `results/harness-two-hour-eval/summary-20260422/summary.json`
- Historical one-shot baseline:
  - `results/oneshot-baseline-summary-20260422/summary.json`

## Local Raw Run Directories

These are the local raw run directories currently relevant to this branch.

### SWE-bench Lite Selected Runs

Use these runs when rebuilding the stable `SWE-bench Lite` thesis summary.

- `results/swebench-lite-pilot/runs/20260422T212019Z`
  - instance: `marshmallow-code__marshmallow-1359`
  - status: `resolved`
- `results/swebench-lite-pilot/runs/20260422T214632Z`
  - instance: `pydicom__pydicom-1694`
  - status: `resolved`
- `results/swebench-lite-pilot/runs/20260423T025929Z`
  - instance: `pylint-dev__astroid-1268`
  - status: `unresolved`
- `results/swebench-lite-pilot/runs/20260423T030947Z`
  - instance: `marshmallow-code__marshmallow-1343`
  - status: `resolved`
- `results/swebench-lite-pilot/runs/20260423T033502Z`
  - instance: `sqlfluff__sqlfluff-2419`
  - status: `empty-patch`

### SWE-bench Lite Exploratory Runs

These runs are useful as discussion evidence, but are intentionally excluded
from the current stable headline summary.

- `results/swebench-lite-pilot/runs/20260422T213823Z`
  - instance: `pylint-dev__astroid-1268`
  - superseded by later selected rerun
  - interpretation: early official-eval failure mode before retry hardening
- `results/swebench-lite-pilot/runs/20260423T032408Z`
  - instance: `sqlfluff__sqlfluff-2419`
  - superseded by later selected rerun
  - interpretation: early agent-side internal-error sample before agent retry hardening
- `results/swebench-lite-pilot/runs/20260423T035156Z`
  - instance: `pvlib__pvlib-python-1606`
  - interpretation: `patch-ready but eval-blocked`
  - current issue: official eval repeatedly fails during instance-image build because
    container-side `git clone https://github.com/pvlib/pvlib-python` times out
- `results/swebench-lite-pilot/runs/20260423T063916Z`
  - instance: `pylint-dev__astroid-1978`
  - interpretation: exploratory `empty-patch`
  - current issue: both agent attempts ended in model-side `APIError`

## How To Reuse After Branch Merge

After merging code branches into the main working branch:

1. Keep this file and the code changes under `experiments/swebench/` and
   `experiments/harness/tests/`.
2. Make sure the merged branch still has access to the same local raw run
   directories under `results/swebench-lite-pilot/runs/`.
3. Regenerate the thesis-facing assets from the merged branch:

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/harness/regenerate_thesis_assets.py
```

4. Verify the regenerated `SWE-bench` summary still reports the same stable
   selected counts before editing the thesis text.

## When To Update This File

Update this file when any of the following changes:

- a new unique pilot instance is promoted into the stable headline set
- an exploratory run is reclassified into the stable set
- a stable run is superseded by a later rerun for the same instance
- a new thesis-facing summary bundle path changes

## Merge Guidance

If there are merge conflicts between branches:

- keep the newest selected-run list for each unique instance
- keep exploratory runs only if they add a new failure mode or debugging value
- prefer the latest regenerated thesis-facing summary paths

This file is intentionally more important than individual stale run directories
for merge decisions.
