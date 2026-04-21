# Documentation Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate scattered root-level project documents into a smaller `docs/` information architecture while preserving all important content and making current project status easier to understand.

**Architecture:** Keep the repository root minimal by retaining only the global entry files, move detailed operational and research records into `docs/overview/` and `docs/research/`, and rewrite the root `README.md` as the single navigation entrypoint. Preserve existing thesis drafts under `experiments/harness/` and add indexes rather than relocating those large writing artifacts.

**Tech Stack:** Markdown, repository file moves, link updates, ripgrep verification

---

### Task 1: Build the new overview and research document skeleton

**Files:**
- Create: `docs/README.md`
- Create: `docs/overview/current-status.md`
- Create: `docs/overview/roadmap.md`
- Create: `docs/overview/session-handoff.md`
- Create: `docs/research/README.md`
- Create: `docs/research/thesis-log.md`

- [ ] **Step 1: Draft the new doc responsibilities**

```text
docs/README.md                 -> top-level docs map
docs/overview/current-status.md -> verified state, active tracks, blockers, next actions
docs/overview/roadmap.md        -> goals and phased plan
docs/overview/session-handoff.md -> shortest resume note
docs/research/README.md         -> thesis/research index and pointers
docs/research/thesis-log.md     -> migrated thesis activity log
```

- [ ] **Step 2: Write the new Markdown files with merged content**

```text
Copy and compress content from the old root docs:
- DEVELOPMENT_LOG.md -> current-status.md
- PROJECT_ROADMAP.md -> roadmap.md
- SESSION_BRIEF.md -> session-handoff.md
- THESIS_LOG.md -> thesis-log.md
Add a docs index that points to these files and to the existing thesis drafts in experiments/harness/.
```

- [ ] **Step 3: Verify the new skeleton exists**

Run: `find docs -maxdepth 3 -type f | sort`
Expected: includes the new overview/research files plus the existing `docs/superpowers/plans/...` entries.

### Task 2: Move or retire root-level operational docs

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Move: `DEVELOPMENT_LOG.md -> docs/overview/current-status.md`
- Move: `PROJECT_ROADMAP.md -> docs/overview/roadmap.md`
- Move: `SESSION_BRIEF.md -> docs/overview/session-handoff.md`
- Move: `THESIS_LOG.md -> docs/research/thesis-log.md`
- Move: `ACP_AGENT_SKILLS_PLAN.md -> docs/archive/acp-agent-skills-plan.md`

- [ ] **Step 1: Move the old root files into their new homes**

```bash
mkdir -p docs/overview docs/research docs/archive
mv DEVELOPMENT_LOG.md docs/overview/current-status.md
mv PROJECT_ROADMAP.md docs/overview/roadmap.md
mv SESSION_BRIEF.md docs/overview/session-handoff.md
mv THESIS_LOG.md docs/research/thesis-log.md
mv ACP_AGENT_SKILLS_PLAN.md docs/archive/acp-agent-skills-plan.md
```

- [ ] **Step 2: Rewrite root entry files**

```text
README.md should explain:
- what the repository is
- the three active workstreams
- where to read current status, roadmap, handoff, and research docs

AGENTS.md should keep working rules but point readers at the new docs paths.
```

- [ ] **Step 3: Verify the root is reduced**

Run: `find . -maxdepth 1 -type f | sort`
Expected: root no longer contains the migrated operational docs.

### Task 3: Repair internal links and references

**Files:**
- Modify: `docs/overview/current-status.md`
- Modify: `docs/overview/roadmap.md`
- Modify: `docs/overview/session-handoff.md`
- Modify: `docs/research/thesis-log.md`
- Modify: `experiments/harness/THESIS_ASSET_MATRIX_ZH.md`
- Modify: `experiments/harness/THESIS_OUTLINE_ZH.md`
- Modify: `experiments/harness/THESIS_FULL_DRAFT_ZH.md`
- Modify: `experiments/harness/THESIS_CHAPTER_ZH.md`

- [ ] **Step 1: Replace stale root-path references**

```bash
rg -n "DEVELOPMENT_LOG\\.md|PROJECT_ROADMAP\\.md|SESSION_BRIEF\\.md|THESIS_LOG\\.md|ACP_AGENT_SKILLS_PLAN\\.md" -S .
```

Expected: only references that are either updated or intentionally mention historical names.

- [ ] **Step 2: Update thesis-facing references**

```text
Point thesis documents to:
- docs/overview/roadmap.md
- docs/research/thesis-log.md
Use absolute repository paths where those documents already use absolute file links.
```

- [ ] **Step 3: Re-run search to verify**

Run: `rg -n "DEVELOPMENT_LOG\\.md|PROJECT_ROADMAP\\.md|SESSION_BRIEF\\.md|THESIS_LOG\\.md" -S .`
Expected: no broken live references remain.

### Task 4: Record the documentation reorganization and summarize status

**Files:**
- Modify: `.codex/project-journal.md`

- [ ] **Step 1: Append a concise project journal entry**

```text
Record:
- root docs were consolidated into docs/overview and docs/research
- root README/AGENTS were updated as new entry points
- thesis draft files remained under experiments/harness with new indexing
```

- [ ] **Step 2: Verify changed files are visible in git status**

Run: `git status --short`
Expected: shows the moved and rewritten docs.

- [ ] **Step 3: Prepare the user-facing progress summary**

```text
Summarize:
- webapp status
- oneshot runner status
- harness status
- research/thesis status
- main blockers and next likely moves
```
