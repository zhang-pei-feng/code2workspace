# Harness Configs

Place future harness configuration files here.
This directory stores stable harness configuration files.

Current files:

- `baseline_layout.toml`
  - the run artifact contract shared with one-shot experiments
- `repo_splits.toml`
  - the first train / holdout repository grouping
- `code2workspace_harness.toml`
  - the current local harness config
  - exposes the one-shot prompt and completion rubric as editable surfaces
  - defines the first train / holdout repository split
  - can optionally point `[proposer].command` at a local proposer script
