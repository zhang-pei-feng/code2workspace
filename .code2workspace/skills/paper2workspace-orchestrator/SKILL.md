---
name: paper2workspace-orchestrator
description: Enforce a strict two-phase repository-to-workspace execution workflow when the user asks to inspect a repository, build a real image, run real validation, generate WDL artifacts, and only then run local Cromwell or Bio-OS workflow execution. Use the current code2workspace task/subagent system instead of the legacy paper2workspace ACP agent.
---

# Paper2Workspace Orchestrator

Use this skill when the user wants the current main agent to turn a repository
into a runnable validated workspace.

## Required behavior

1. Treat the task as a strict two-phase workflow.
2. Phase 1: repository inspection, exact Dockerfile/image work, real validation.
3. Phase 2: WDL/Bio-OS or local Cromwell execution.
4. Never start phase 2 until phase 1 artifacts exist on disk.
5. Prefer the `workspace-builder` subagent for long execution branches.

## Local helpers

- Create a run layout:
  `python3 skills/paper2workspace-orchestrator/scripts/workspace_tool.py init --repo "<repo-name>"`
- Check whether phase 2 may begin:
  `python3 skills/paper2workspace-orchestrator/scripts/workspace_tool.py phase2-ready --run-dir "<run-dir>"`
- Check completion:
  `python3 skills/paper2workspace-orchestrator/scripts/workspace_tool.py completion --run-dir "<run-dir>"`

## Rules

- Never call the old `paper2workspace_agent` ACP runtime.
- Never declare completion from plans or drafted files alone.
- Save outputs under `results/skills/paper2workspace-orchestrator/<repo>/<timestamp>/`.
- Preserve exact filenames the user asked for.
