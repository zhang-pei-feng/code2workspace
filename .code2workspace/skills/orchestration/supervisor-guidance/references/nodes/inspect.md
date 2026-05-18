# Inspect Node Guidance

- If the task names a repository URL and the source tree is absent, materialize the repository into the current workspace before deeper inspection.
- If the repository is already materialized in the current workspace, inspect that local copy directly instead of re-cloning it.
- Prefer concrete build/test entrypoints and bundled datasets over speculative assumptions.
- Return specific downstream prerequisites for build, workflow validation, and writable output paths.
