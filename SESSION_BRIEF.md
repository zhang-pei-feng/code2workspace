# Session Brief

New session instructions:

Start with `DEVELOPMENT_LOG.md`, then read `PROJECT_ROADMAP.md`, `THESIS_LOG.md`,
and the README files under `apps/webapp` and `experiments/oneshot`. The current
priority is to keep the LangGraph-backed web MVP stable, harden the generic
one-shot batch runner after the observed `Flye` clone failure, finish the
remaining repo baselines, and only then turn the resulting prompts / policies
into a repeatable harness workflow. `spades` is already the successful heavy
baseline; the current weak point is batch orchestration, not shell capability.
Check `experiments/harness/README.md` and
`experiments/harness/configs/repo_splits.toml` before changing the experiment
surface or repo grouping. Also note the current local worktree state: webapp
tests are green, but `experiments/oneshot/tests` are not yet green because the
repo-preparation hardening refactor changed the `ensure_repo(...)` call shape
without updating the test monkeypatches. Update the logs before and after
meaningful changes so the next session can resume without rediscovering
repository state.
