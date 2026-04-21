---
name: deep-research-report
description: Orchestrate multi-lane deep research and materialize a report when the user asks for deep research, report writing, source-backed synthesis, or a thorough answer that should combine literature, monitoring, and local database evidence. Use the current code2workspace task subagents and local skills instead of the legacy open_deep_research ACP agent.
---

# Deep Research Report

Use this skill for long-form source-backed research where the answer should be a
report rather than a short reply.

## Default approach

1. Break the task into 2-4 research lanes.
2. Delegate each lane to `research-lane` with a concrete evidence target.
3. Prefer existing project skills as evidence layers:
   - `academic-search`
   - `respiratory-disease-wide-monitor`
   - `virus-variation-query`
4. Materialize the report directory with:
   `python3 skills/deep-research-report/scripts/report_tool.py init --topic "<topic>"`
5. Save lane notes as markdown under `lanes/*.md`, each with:
   - `Skill: ...`
   - `Source: ...`
   - real narrative evidence beyond metadata-only lines
6. After lane notes exist, compose the report with:
   `python3 skills/deep-research-report/scripts/report_tool.py compose --run-dir "<run-dir>"`
7. Return the report path plus a short summary of the conclusion and evidence layers used.

## Rules

- Never call the legacy `open_deep_research` ACP wrapper or its session store.
- Do not promise a report before lane notes or sources exist.
- Save outputs under `results/skills/deep-research-report/...`.
- The final report must contain a `Sources` section.
- `compose` now writes both `final_report.md` and `report_diagnostics.json`.
- A metadata-only lane does not count as complete evidence.

## Output rules

- Mention the report directory first.
- Summarize the research conclusion briefly.
- List the evidence layers actually used.
- If diagnostics say the report is incomplete, say so explicitly instead of pretending the synthesis is fully covered.
