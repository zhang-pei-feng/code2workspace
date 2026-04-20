# Skill Tests

This directory contains the live evaluation framework for project skills and
composite report orchestrators.

## Purpose

The goal is to make real natural-language skill testing reproducible and
machine-readable rather than leaving it as ad hoc terminal sessions.

## Layout

- `cases/`
  - TOML case definitions for live evaluations
- `runner.py`
  - executes live cases, captures logs, extracts behaviors, and classifies
    outcomes
- `parsers.py`
  - log parsers for tool calls, subagent references, summary lines, and repo
    paths
- `report.py`
  - writes machine-readable and Chinese markdown summaries
- `tests/`
  - deterministic tests for case loading, parser behavior, matcher behavior,
    and summary generation

## Run

From the repository root:

```bash
PYTHONPATH=/mnt/data1/zhangpf/code2workspace \
uv run --project libs/cli python experiments/skill_tests/runner.py \
  --date 20260420 \
  --case academic-search-positive.toml
```

List all known cases:

```bash
PYTHONPATH=/mnt/data1/zhangpf/code2workspace \
uv run --project libs/cli python experiments/skill_tests/runner.py --list-cases
```

Run the fixed COVID monitoring question batch into `experiments/...`:

```bash
PYTHONPATH=/mnt/data1/zhangpf/code2workspace \
uv run --project libs/cli python experiments/skill_tests/run_question_batch.py
```

This path tests direct natural-language questions against `code2workspace`
without explicitly telling it to invoke any particular skill. The batch prompt
list lives under `experiments/skill_tests/batches/`, and the run artifacts live
under `experiments/skill_tests/runs/`.

## Output

Results are written to:

```text
results/skill-tests/<YYYYMMDD>/
```

Each run writes:

- `<case>.prompt.txt`
- `<case>.log`
- `summary.json`
- `SUMMARY_ZH.md`
- `CAPABILITY_SNAPSHOT_ZH.md` (输入 + 全量最终回答输出，已过滤 tool trace)

## Status model

Each case is classified as exactly one of:

- `passed`
- `behavior_regression`
- `infra_blocked`
- `known_issue`
- `runner_error`
