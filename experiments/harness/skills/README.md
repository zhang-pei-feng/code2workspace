# Imported Skills

This directory stores imported skill material that the local harness can reuse
as reference surfaces or prompt/tooling examples.

## Current source

- OpenClaw workspace skills from `/home/zhangpf/.openclaw/workspace/skills`

## Local layout

- `openclaw/`
  - imported `SKILL.md` trees and lightweight guide files
  - excludes archived tarballs and the very large local prompt bundle payloads

## Refresh command

```bash
uv run --project libs/cli python experiments/harness/import_openclaw_skills.py --clean
```
