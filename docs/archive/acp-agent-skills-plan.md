# ACP Agent Skills Plan

## Goal

Move four legacy superagent capabilities into project-level `code2workspace`
skills and project subagents. Runtime use of old ACP / DeepAgents agents is not
allowed. The old repositories are migration references only.

## Constraints

- New public skills live in `.code2workspace/skills/`.
- New custom subagents live in `.code2workspace/agents/`.
- Shared helper code lives in `.code2workspace/skills/_shared-superagent-helpers/`
  and must not contain `SKILL.md`.
- New run outputs live under `results/skills/<skill-name>/`.
- Do not call `acpx benchmark_agent`, old `run-acp.sh`, old ACP servers, or old
  private DeepAgents homes at runtime.

## Public Skills

1. `benchmark-workflow-orchestrator`
   - Local workflow reuse, batch benchmark orchestration, result collection,
     benchmark summarization.
2. `data-governance-ops`
   - Source brief, snapshot refresh, latest snapshot query, history compare,
     quality triage, optional local DB querying.
3. `deep-research-report`
   - Deep research lane orchestration and report materialization.
4. `paper2workspace-orchestrator`
   - Strict two-phase repo-to-workspace execution with artifact gating.

## Project Subagents

1. `governance-operator`
2. `research-lane`
3. `workspace-builder`

These subagents are prompt-defined only. They do not rely on automatic
`SkillsMiddleware` injection and must explicitly read the relevant local skill
files or run the relevant local scripts.

## Current Status

- [x] Create project plan document.
- [x] Create shared helper scaffolding and reusable result-dir helpers.
- [x] Add `benchmark-workflow-orchestrator`.
- [x] Add `paper2workspace-orchestrator`.
- [x] Add `deep-research-report`.
- [x] Add `data-governance-ops`.
- [x] Add four project subagents.
- [x] Add smoke tests for project skill and subagent discovery.
- [x] Verify project skill discovery through CLI / loader.
- [x] Verify project subagent discovery through loader.

## Verification Notes

- Skill discovery is validated against `.code2workspace/skills`.
- Subagent discovery is validated against `.code2workspace/agents`.
- Shared helper scripts expose `--help`.
- Data governance helper can create a real local snapshot bundle and compare it.
- Deep research helper can materialize a report from lane notes.
- Paper2workspace helper can gate phase progression from real filesystem
  artifacts.

## Follow-Up

- Keep workflow execution local and remove remote-service assumptions from older
  migration notes when they are no longer relevant.
- Expand data-governance live fetch coverage beyond the minimal `ncbi_virus`
  path implemented locally here.
- Add richer report composition and citation merging for the deep-research skill.
