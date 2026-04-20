# One-Shot Experiments

This directory contains the first generic repo-task runner for the Docker + WDL
workflow tasks.

## Purpose

Given only a GitHub repository URL, the runner should:

- clone the repository
- derive a standard one-shot task prompt
- execute `code2workspace` once
- capture raw terminal output
- persist prompt, metadata, logs, and summary

## Current scripts

- `tasks.py`
  - prompt generation, repo-name normalization, and target list loading
- `run_repo_task.py`
  - clone / run / log / summarize entrypoint for one repository
- `run_repo_batch.py`
  - sequential batch entrypoint for `targets.txt` or another repo list

## Artifact contract

Each run directory now contains:

- `prompt.txt`
- `manifest.json`
- `agent.log`
- `summary.json`

## Run example

From the repository root:

```bash
uv run --project libs/cli python experiments/oneshot/run_repo_task.py \
  https://github.com/ablab/spades
```

The default timeout is now 30 minutes per repository run. You can override it:

```bash
uv run --project libs/cli python experiments/oneshot/run_repo_task.py \
  https://github.com/ablab/spades \
  --max-runtime-minutes 60
```

## Initial target list

See `targets.txt`.

## Batch example

```bash
uv run --project libs/cli python experiments/oneshot/run_repo_batch.py \
  --limit 2 \
  --max-runtime-minutes 30
```

## Notes

- This is intentionally one-shot only.
- The runner persists the exact prompt and terminal output so later harness work
  can compare runs without reconstructing context from memory.
- The default prompt template now comes from
  `experiments/harness/surfaces/one_shot_prompt.txt` so harness edits and
  one-shot execution share the same surface.
- The completion judgment now comes from
  `experiments/harness/surfaces/completion_rubric.txt` through
  `experiments/oneshot/completion.py`, and each `summary.json` includes a
  structured `completion_judgment` evidence block instead of only a keyword check.
- The runner now enables shell execution explicitly with `--shell-allow-list all`;
  without this, Docker/WDL tasks cannot be executed honestly in non-interactive mode.

## Current empirical state

- `spades` has already been pushed through the full Docker + WDL path to a real
  successful baseline and remains the reference heavy-repo case.
- The repo-specific baseline notes now live alongside the run artifacts:
  - `results/oneshot/spades/BASELINE_NOTES.md`
  - `results/oneshot/canu/BASELINE_NOTES.md`
  - `results/oneshot/megahit/BASELINE_NOTES.md`
  - `results/oneshot/v-pipe/BASELINE_NOTES.md`
- The first batch over the remaining repositories produced two useful timeout
  baselines with real build evidence:
  - `canu` reached real Docker build execution, initialized submodules, and then
    spent the 30-minute budget inside first-build dependency installation
  - `megahit` converged on the repo-native `--test` path, entered real Docker
    build execution, and then spent the 30-minute budget inside first-build
    dependency installation
- `v-pipe` is now a completed non-`spades` positive baseline:
  - the run built the image, executed a real HIV test dataset in-container, and
    then reached Cromwell `Succeeded`
  - the direct container artifact and the WDL-copied artifact match by SHA256,
    giving a clean evidence-backed completion case
- The current batch weakness is repository preparation, not prompt generation:
  - `Flye` exposed that a transient `git clone` transport failure can still abort
    the whole batch before `_batch/.../batch_summary.json` is written
  - clone/setup failure handling is now hardened so this class of failure becomes
    a recorded per-repository outcome rather than an untracked batch crash
- The current heavy-repo next step is therefore narrower than before:
  - keep `canu` and `megahit` on the same minimal prompt surface
  - rerun them with longer build budgets or warmer base-image layers instead of
    reopening prompt discovery
