# Session Handoff

Use this file when starting a fresh session and you want the shortest useful
resume path.

## Read Order

1. `docs/overview/current-status.md`
2. `docs/overview/roadmap.md`
3. `docs/research/thesis-log.md`
4. `docs/overview/supervisor-flow-experiment-status.md`
5. `apps/webapp/README.md`
6. `experiments/oneshot/README.md`
7. `experiments/harness/README.md`

## Current Priority

On branch `feature/supervisor-graph-runtime`, keep the supervisor-first runtime
as the active long-task path. The default CLI agent should enter the Supervisor
Graph wrapper first, with `github2workspace`, `benchmark`, `report`, and
generic task families handled by the shared runtime rather than the old soft
planner middleware.

## Current State To Remember

- `spades` is already the reference heavy-repo success case.
- `v-pipe` is the strongest additional non-`spades` positive baseline.
- `canu` and `megahit` are no longer blocked on task discovery or shell access;
  they mostly burn time on first-build dependency setup.
- repository-preparation failures are now treated as explicit experiment
  outcomes instead of queue-killing crashes.
- model configuration on this branch is intended to use the project-local
  `backend/config/agent_models.json` entry, while legacy/test TOML support and
  normal `.env` / environment-variable loading still exist in code.
- Current portability audit is stricter than the historical runtime baseline:
  `backend/config/agent_models.json` is the intended project-local model config
  entry, but normal runtime still reads `.env`, provider credential/base-url
  environment variables, report-worker model override variables, and some
  skill-specific external credentials. See
  `docs/overview/supervisor-flow-experiment-status.md` before claiming strict
  portability or single-entry configuration.
- Supervisor Graph routing should keep the special `github2workspace`,
  `benchmark`, and `report` lanes available; generic tasks use the generic graph
  instead of a QA-only forced mode.
- the interactive TUI startup hotfix is in; it now reaches the ready prompt
  again, so treat it as usable unless a deeper interaction bug is reproduced.
- normal CLI sessions use isolated project-root workspaces by default; use
  `--session-workdir-mode inherit` only when explicitly needed.

## Before Changing Experiment Surfaces

- read `experiments/harness/README.md`
- check `experiments/harness/configs/repo_splits.toml`
- treat the current one-shot prompt and completion rubric as live harness
  surfaces, not throwaway notes

## Maintenance Rule

Update `docs/overview/current-status.md` and `docs/research/thesis-log.md` after
meaningful changes so the next session does not need to rediscover repository
state.
