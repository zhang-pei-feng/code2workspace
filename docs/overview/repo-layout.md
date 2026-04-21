# Repository Layout Policy

This file defines the intended root-level layout for `code2workspace`.

## Stable Source Roots

- `apps/`
  - small application entrypoints such as the web API backend
- `libs/`
  - reusable runtime and CLI code
- `experiments/`
  - experiment runners, benchmark assets, harness code, and reusable test cases
- `docs/`
  - repository-facing status, research notes, archive material, and planning docs
- `.code2workspace/`
  - project-local agent config, skills, and related metadata

## Stable Generated Roots

- `results/`
  - retained experiment outputs and benchmark evidence
- `.workspaces/`
  - large historical workspaces and heavy intermediate run state
- `workspace/`
  - per-session CLI working directories
- `tmp/`
  - disposable local scratch outputs

## Compatibility And Cache Paths

- `skills/`
  - compatibility symlink to `.code2workspace/skills`; do not create a second
    independent skills tree at the repository root
- `.pytest_cache/`, `.benchmarks/`, `cromwell-workflow-logs/`, `__pycache__/`
  - disposable local cache or runtime byproducts; keep them ignored and remove
    them freely when cleaning the repo

## Placement Rules

- New product or runtime code belongs under `libs/` or `apps/`.
- New experiment code belongs under `experiments/`.
- New long-lived experiment outputs belong under `results/`, not under
  `apps/`, `libs/`, or new root directories.
- New session or scratch outputs should reuse `workspace/`, `.workspaces/`, or
  `tmp/` instead of creating additional root-level output folders.
- Current directory names stay as they are unless a future cleanup changes the
  policy deliberately.
