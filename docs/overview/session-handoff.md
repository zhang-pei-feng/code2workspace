# Session Handoff

Use this file when starting a fresh session and you want the shortest useful
resume path.

## Read Order

1. `docs/overview/current-status.md`
2. `docs/overview/roadmap.md`
3. `docs/research/thesis-log.md`
4. `apps/webapp/README.md`
5. `experiments/oneshot/README.md`
6. `experiments/harness/README.md`

## Current Priority

Keep the LangGraph-backed web MVP stable, continue hardening the generic
one-shot runner, finish the remaining high-value repo baselines, and then spend
the next serious effort on the harness loop rather than more ad hoc prompt
tweaks.

## Current State To Remember

- `spades` is already the reference heavy-repo success case.
- `v-pipe` is the strongest additional non-`spades` positive baseline.
- `canu` and `megahit` are no longer blocked on task discovery or shell access;
  they mostly burn time on first-build dependency setup.
- repository-preparation failures are now treated as explicit experiment
  outcomes instead of queue-killing crashes.
- the web UI is green enough for control-plane use; keep it simple and do not
  overbuild chat UX yet.
- the interactive TUI startup hotfix is in; it now reaches the ready prompt
  again, so treat it as usable unless a deeper interaction bug is reproduced.

## Before Changing Experiment Surfaces

- read `experiments/harness/README.md`
- check `experiments/harness/configs/repo_splits.toml`
- treat the current one-shot prompt and completion rubric as live harness
  surfaces, not throwaway notes

## Maintenance Rule

Update `docs/overview/current-status.md` and `docs/research/thesis-log.md` after
meaningful changes so the next session does not need to rediscover repository
state.
