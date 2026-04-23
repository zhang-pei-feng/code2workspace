# SWE-bench Pilot

This directory contains a lightweight `SWE-bench Lite` pilot path for thesis-facing
evidence.

## Scope

- small local subset only
- official `swebench` evaluation harness
- `code2workspace` generates the patch inside a checkout at the benchmark base commit
- thesis-ready summary bundle via `summarize_swebench_lite.py`

## Default subset

See `pilot_instances.txt`.

The current default subset prioritizes smaller Python repositories from the
`dev` split so the first pilot can run within the current disk/time budget.

## Run

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/swebench/run_swebench_lite_pilot.py \
  --instance-limit 1 \
  --use-hints \
  --agent-retries 1 \
  --official-eval-retries 1
```

The official evaluation step uses the local `.venv-swebench` environment and
forces `--namespace none` so Docker images are built locally instead of pulled
from Docker Hub.

`--agent-retries` retries the non-interactive agent run only when a run ends
with an empty patch plus an obvious transient model-side error such as
`InternalServerError` or `RemoteProtocolError`.

`--official-eval-retries` controls how many additional official-eval retries are
attempted when a run ends in harness-level `error_ids`. Each retry writes its
own log file and the final `evaluation_payload.json` records
`report.evaluation_attempts`.

## Summarize

```bash
PYTHONPATH=. uv run --project libs/cli python experiments/swebench/summarize_swebench_lite.py
```
