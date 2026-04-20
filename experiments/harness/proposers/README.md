# Proposer Commands

This directory stores local proposer commands for the harness outer loop.

The harness now supports two outer-loop modes:

- `[proposer].command`
  - run one local script inside the proposer workspace
- `[better_agent]`
  - run a native deepagents outer proposer against the same workspace contract

## Contract

The harness builds one proposer workspace per iteration and then runs the
configured `[proposer].command` with:

- current working directory set to that proposer workspace
- `CODE2WORKSPACE_HARNESS_WORKSPACE`
  - absolute path to the proposer workspace root
- `CODE2WORKSPACE_HARNESS_CURRENT`
  - absolute path to the editable `current/` directory
- `CODE2WORKSPACE_HARNESS_PROPOSAL`
  - absolute path to `proposal.md`

The proposer is expected to:

- read `task.md`, `surface_manifest.json`, `train_summary.json`, and `train_failures.json`
- edit only files under `current/`
- update `proposal.md`

The harness then materializes `current/` back into one candidate variant and
decides whether to keep or discard it based on combined `train + holdout`
passes.

## Included Script

- `noop_proposer.py`
  - smoke test only
  - writes `proposal.md` and makes no harness changes
