---
name: epidemic-warning-report
description: Generate a source-backed epidemic prevention and early-warning report when the user asks for a situation report, surveillance brief, risk assessment, epidemic warning, weekly update, prevention summary, monitoring synthesis, or a comprehensive report about COVID-19, influenza, RSV, respiratory pathogens, variants, immune escape, vaccine progress, or outbreak signals. Use this skill to orchestrate existing local evidence skills rather than answering from one source only. The report should combine official monitoring, source-catalog or channel context when useful, local variant or lineage database evidence when relevant, and literature or clinical evidence when mechanism, vaccine, or trial progress matters.
---

# Epidemic Warning Report

Use this skill when the user wants a formal or semi-formal report rather than a
short answer, especially for epidemic prevention, surveillance warning, or risk
assessment.

Unless the user explicitly asks for a short brief, the default output should be
a **long-form report of at least 5000 Chinese characters**. The report should
read like a real analytical brief, not like a directory manifest or a thin
bullet skeleton.

## Typical triggers

- “生成一个疫情预警报告”
- “做一个较全面的监测简报”
- “给我一个新冠/流感/RSV 风险研判”
- “做一份本周呼吸道病原监测报告”
- “帮我汇总最近的疫情信号并给出防控建议”
- “写一个 source-backed 的变异株风险与疫苗进展报告”

## Deep-Research Style Structure

This skill should be run in a deep-research style rather than as a single,
serial reasoning pass.

Default pattern:

1. initialize a report run directory
2. launch multiple bounded subagents in parallel
3. save each lane result into `lanes/*.md`
4. optionally run a synthesis subagent
5. compose the final report from the lane files

For a full warning report, the first four lanes are required evidence lanes:

- `01_official-monitoring.md`
- `02_source-catalog.md`
- `03_variant-risk.md`
- `04_literature-clinical.md`

An empty lane or a lane without both `Skill:` and `Source:` metadata does not
count as covered evidence.

The main agent remains the orchestrator. The specialized evidence gathering
should be delegated to project subagents with different roles and prompts.

## Default report length and detail level

- Default minimum final report length: **5000 Chinese characters**
- Default lane target:
  - `01_official-monitoring.md`: 900-1500 Chinese characters
  - `02_source-catalog.md`: 700-1200 Chinese characters
  - `03_variant-risk.md`: 700-1200 Chinese characters when relevant
  - `04_literature-clinical.md`: 900-1500 Chinese characters
  - `05_actions.md`: 700-1200 Chinese characters
- If the user explicitly asks for a short brief, shorter output is allowed.
- If a lane is not relevant, say so explicitly; do not replace it with an empty
  stub.

## Evidence model

Do not rely on one source only unless the user explicitly asks for a narrow
report. Default to 2-4 evidence layers selected from:

1. **Official monitoring layer**
   - Use `respiratory-disease-data-fetcher` when the user clearly wants a small
     fixed set of WHO / CDC / China CDC quick results.
   - Otherwise prefer `respiratory-disease-wide-monitor` for broader monitoring
     coverage from the source table.

2. **Source catalog / channel layer**
   - Use `epietl-api` when the report benefits from source-channel context,
     source types, source URLs, dashboards, report collections, or structured
     data-source references.

3. **Local variant / mutation layer**
   - Use `virus-variation-query` when the report asks about a lineage, mutation,
     immune escape, RBD / Spike changes, or local DB evidence.

4. **Literature / clinical layer**
   - Use `academic-search` when the report needs papers, preprints, vaccine
     progress, mechanistic explanation, neutralization evidence, or clinical
     trial context.

5. **Web augmentation layer**
   - For long-form reports, you may and should enrich the report with recent
     source-backed web context using:
     - `web_search` when available
     - `fetch_url` / web fetch for official pages, dashboards, reports, and
       public updates
   - Prefer official and primary sources such as WHO, CDC, China CDC, ECDC,
     national health ministries, or peer-reviewed journal pages.
   - Do not use generic low-credibility pages to pad length.

## Parallel subagents

Use these project subagents for bounded, parallel lanes:

- `epidemic-monitor-analyst`
- `epidemic-source-cartographer`
- `epidemic-variant-analyst`
- `epidemic-clinical-analyst`
- `epidemic-report-composer` optional after lane notes exist

### Lane mapping

- `lanes/01_official-monitoring.md`
  - subagent: `epidemic-monitor-analyst`
- `lanes/02_source-catalog.md`
  - subagent: `epidemic-source-cartographer`
- `lanes/03_variant-risk.md`
  - subagent: `epidemic-variant-analyst`
- `lanes/04_literature-clinical.md`
  - subagent: `epidemic-clinical-analyst`
- synthesis note or action note
  - subagent: `epidemic-report-composer` optional

### Delegation rules

- Launch the first 3-4 evidence lanes in parallel whenever they are independent.
- Give each subagent a bounded objective and the exact file it should produce.
- Each lane should return **detailed analytical markdown**, not only thin
  bullets or metadata.
- Require each lane to include `Skill:` and `Source:` lines for later merging.
- Do not let one subagent perform all evidence gathering unless the user
  explicitly asks for a narrow report.
- If a lane has enough domain evidence but still lacks operational detail,
  allow that lane to augment itself with `web_search` and `fetch_url`.

## Required workflow

1. Initialize a report run directory:

```bash
python3 skills/epidemic-warning-report/scripts/epidemic_report_tool.py init \
  --topic "<report topic>" \
  --pathogen "<pathogen or mixed>" \
  --region "<region>" \
  --period "<time window>"
```

2. Write lane notes under the generated `lanes/` directory. At minimum:
   - `01_official-monitoring.md`
   - `02_source-catalog.md`
   - `03_variant-risk.md`
   - `04_literature-clinical.md`

3. Launch the first evidence lanes in parallel with the task tool, for example:

```text
task(subagent_type="epidemic-monitor-analyst", description="...write lanes/01_official-monitoring.md ...")
task(subagent_type="epidemic-source-cartographer", description="...write lanes/02_source-catalog.md ...")
task(subagent_type="epidemic-variant-analyst", description="...write lanes/03_variant-risk.md ...")
task(subagent_type="epidemic-clinical-analyst", description="...write lanes/04_literature-clinical.md ...")
```

4. After evidence lanes exist, optionally launch:

```text
task(subagent_type="epidemic-report-composer", description="Read the lane notes, decide risk level, draft executive summary and actions.")
```

5. Each lane note should keep concrete evidence. When possible, include lines
   starting with:
   - `Source: ...`
   - `Skill: ...`
   - at least one short evidence statement beyond metadata-only lines
   - enough narrative detail that the final composed report can exceed 5000
     Chinese characters without looking padded

6. Compose the final report:

```bash
python3 skills/epidemic-warning-report/scripts/epidemic_report_tool.py compose \
  --run-dir "<run-dir>"
```

## Report requirements

The final report should contain these sections unless the user explicitly asks
for a shorter structure:

- Executive Summary
- Monitoring Overview
- Key Risk Signals
- Variant / Pathogen Notes
- Source and Coverage Analysis
- Literature and Clinical Context
- Risk Level Rationale
- Prevention and Preparedness Actions
- Operational Recommendations
- Uncertainty and Data Gaps
- Sources

## Writing rules

- State the output directory first.
- Make the risk judgment explicit: `Low`, `Moderate`, `Elevated`, or `High`,
  and explain why.
- Default to a detailed long-form report. Unless the user asks for brevity,
  do not stop at a short memo or a few bullets.
- The final report should normally exceed **5000 Chinese characters**.
- Preserve the multi-lane structure even if you later compress the final prose.
- If one evidence layer is unavailable, say so explicitly; do not invent a
  complete report around missing evidence.
- Do not treat a report as complete if the required core lanes are missing.
- The compose helper will record lane completeness diagnostics; use them instead
  of silently masking missing evidence.
- Do not use path listings, manifest echoes, or section headers as fake detail.
  Add real analytical narrative, source comparison, interpretation, and action
  reasoning.
- When the report includes variant, vaccine, or immune-barrier interpretation,
  do not present local DB results as clinical conclusions by themselves. Pair
  them with literature or official monitoring when possible.
- Keep action recommendations operational and concrete:
  surveillance, sequencing, clinical preparedness, risk communication, data-gap
  follow-up.
- If `web_search` is unavailable in the current runtime, fall back to
  `fetch_url` and existing evidence skills; state that limitation instead of
  pretending a broader web survey happened.
- The `Sources` section must list only the sources actually used.

## Output location

Save all artifacts under:

```text
results/skills/epidemic-warning-report/
```
