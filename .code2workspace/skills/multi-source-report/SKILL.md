---
name: multi-source-report
description: Generate a source-backed long-form report when the user asks for deep research, a formal report, a risk assessment, a monitoring brief, a warning-style synthesis, or any cross-source written analysis that should combine multiple evidence layers instead of relying on one source only.
---

# Multi-Source Report

Use this skill when the user wants a written report rather than a short answer.

This is the only report-generation skill in the project. Use it for:

- deep research
- formal reports
- risk assessments
- monitoring briefs
- warning / preparedness syntheses
- cross-source evidence summaries

The workflow follows a deep-research pattern:

1. Plan the report and save the request
2. Create a report run directory
3. Delegate focused research lanes in parallel with `task()`
4. Merge findings into lane notes under `lanes/*.md`
5. Compose `final_report.md`
6. Verify the final report against the original request
7. Return the full report body plus the output directory and evidence layers used

## Research Workflow

Follow this workflow for report requests:

1. Create a todo list with `write_todos`
2. Initialize the run directory:

```bash
python3 skills/multi-source-report/scripts/report_tool.py init \
  --topic "<report topic>" \
  --report-mode "<general|risk>"
```

3. Save or restate the user request in the run metadata if needed
4. Delegate focused research tasks with `task()`; use parallel tasks whenever the lanes are independent
5. Save each lane note under `lanes/*.md`
6. Optionally delegate synthesis to `report-synthesizer`
7. Compose the final report:

```bash
python3 skills/multi-source-report/scripts/report_tool.py compose \
  --run-dir "<run-dir>"
```

8. Read the request and confirm the final report actually answers it

## Delegation Model

Default lane pattern:

- `01_monitoring.md`
  monitoring, operations, official signals
- `02_source-catalog.md`
  source provenance, source coverage, dashboards, channel context
- `03_local-data.md`
  local structured data, local DB, curated tables, repository-local evidence
- `04_literature-web.md`
  papers, technical references, primary-source web context
- `05_synthesis.md`
  cross-lane synthesis and recommendations

Default parallelism:

- Start with 1 `report-researcher` for simple report requests
- Use 2-3 `report-researcher` tasks for comparisons or clearly separate evidence lanes
- Use `report-synthesizer` after the evidence lanes exist

Use `report-researcher` multiple times in parallel rather than introducing lane-specific report subagents.

## Evidence Layers

Prefer current project skills as first-class evidence layers:

- `skills/academic-search/SKILL.md`
- `skills/respiratory-disease-wide-monitor/SKILL.md`
- `skills/respiratory-disease-data-fetcher/SKILL.md`
- `skills/epietl-api/SKILL.md`
- `skills/virus-variation-query/SKILL.md`

Use `fetch_url` and `web_search` only as augmentation when a lane still has a concrete missing evidence gap after using the local/project skills.

Do not rely on generic web pages to pad report length.

## Lane Note Requirements

Every completed lane note must include:

- `Skill: ...`
- `Source: ...`
- real narrative evidence beyond metadata-only lines
- inline numbered citations such as `[1]`, `[2]` when possible

When a lane contains trustworthy numeric evidence, also add one or more table
candidate blocks so compose can build a source-backed Markdown table:

```text
Table Candidate: <title>
Metric: <metric name>
Value: <value>
Unit: <unit or blank>
Time: <time window>
Scope: <region / cohort / population>
Source: <source label>
Note: <short caveat>
```

A metadata-only lane does not count as complete evidence.

If a lane is not relevant, say so explicitly in the lane note instead of silently omitting it.

## Report Requirements

The final report must:

- be written to `final_report.md`
- include a `Sources` section
- preserve source-backed lane content
- include cross-source synthesis, not only a lane dump
- include Markdown tables when reliable numeric evidence exists
- include a risk/severity section only when the request is risk-oriented
- return the full report body to the user, not only a filesystem path

Default minimum length:

- long-form report: 5000 characters unless the user explicitly asks for a shorter brief
- prefer source-backed tables for formal reports when stable numeric evidence is available

## Output Rules

In the final user-facing response:

1. Give the output directory
2. Give the evidence layers used
3. Include the full report body
4. If diagnostics say the report is incomplete, say so explicitly

Do not answer with only `final_report.md` or a local file path.
