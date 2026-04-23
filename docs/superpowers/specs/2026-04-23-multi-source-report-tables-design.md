# Multi-Source Report Long-Form Tables Design

## Summary

Upgrade `multi-source-report` from a pure long-form Markdown report generator
into a more formal report writer that can also emit source-backed Markdown
tables when reliable numeric evidence is available.

This design intentionally does **not** require a chart/image pipeline in v1.
The first enhancement is:

- default `5000+` Chinese characters for formal reports
- source-backed Markdown tables when the evidence contains stable, explainable,
  comparable numeric values
- explicit "no table due to insufficient evidence" behavior when numeric support
  is weak or non-comparable

The existing lane-based multi-source workflow remains the core architecture.

## User-Facing Behavior

### Default output policy

For `multi-source-report` requests that are clearly formal reports, risk
assessments, or monitoring briefs:

- default minimum length becomes `5000` Chinese characters
- if one or more report lanes contain trustworthy numeric evidence, the final
  report should include at least one Markdown table
- if there are two or more meaningful comparable numeric groups, the final
  report may include up to three tables
- if no reliable numeric evidence exists, the report must say so explicitly
  rather than fabricating a table

Short-answer behavior remains available only when the prompt explicitly asks for
brevity.

### Table quality rules

Every table row must be traceable to the report's actual evidence set.

A numeric item may enter a table only if all of the following are true:

- the value appears in a used source or lane note
- the time window is explicit or inferable from the cited evidence
- the metric meaning is clear enough to explain in one short note
- the source can be listed directly in the report

Each table must include, either in the title or immediately adjacent prose:

- what the table summarizes
- the time range or observation window
- the geography / population scope when relevant
- source attribution
- a comparability warning when indicators are not perfectly aligned

## Report Architecture Changes

### Manifest additions

Add the following `manifest.json` defaults for formal report runs:

- `min_report_chars = 5000`
- `prefer_tables = true`
- `max_tables = 3`

These are defaults, not hard overrides. The prompt can still request shorter or
table-free output.

### Lane note contract

Lane notes continue to require:

- `Skill: ...`
- `Source: ...`
- narrative evidence

Add an optional structured table-candidate block to lane notes.

Recommended v1 format:

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

Multiple candidate rows may appear in one lane.

This keeps the current free-form narrative model intact while giving compose a
safe structured extraction target.

### Compose-stage behavior

`report_tool.py` compose should:

1. parse the usual lane metadata and narrative evidence
2. additionally extract table-candidate rows from lane notes
3. group rows into small, coherent Markdown tables
4. insert those tables into the final report after the relevant analytical
   section or under a dedicated `Key Data Tables` section
5. fall back to a short explicit statement when no reliable rows qualify

The compose step should remain deterministic and conservative:

- do not infer missing values
- do not merge rows with incompatible scopes unless explicitly labeled
- do not create a table from only one vague numeric fragment

## Diagnostics And Validation

### Diagnostics additions

Extend `report_diagnostics.json` with:

- `table_count`
- `table_candidate_count`
- `table_rows_used`
- `table_rows_rejected`
- `table_rejection_reasons`

This makes table behavior auditable and helps distinguish:

- no numeric evidence available
- numeric evidence available but not comparable
- numeric evidence available and successfully tabulated

### Test plan

Add tests at three levels:

1. Tool/unit level
   - `compose` inserts at least one Markdown table when valid candidate rows
     exist
   - `compose` does not create a table from metadata-only or weak numeric input
   - `report_diagnostics.json` records used and rejected rows correctly

2. Contract level
   - formal report mode defaults to `5000+` characters
   - risk-oriented reports can still include risk framing plus tables
   - when evidence is insufficient, the report states that no table was
     produced because the numeric evidence is inadequate

3. End-to-end level
   - a live or fixture-backed report case yields:
     - long-form report
     - at least one table when numeric evidence exists
     - explicit sources for the table data

## Scope Boundaries

Included in this design:

- long-form default for formal reports
- Markdown table generation
- conservative numeric extraction from lane notes
- source and time attribution for tables
- diagnostics and tests

Explicitly excluded from v1:

- automatic PNG/SVG chart rendering
- chart styling/themes/assets
- OCR or PDF figure extraction
- free-form model-generated charts not backed by structured numeric rows

## Defaults Chosen

- Formal `multi-source-report` output defaults to `5000+` Chinese characters.
- Tables are preferred when reliable numeric evidence exists.
- Markdown tables are the only structured data-display format in v1.
- Charts remain optional future work, not part of this implementation.
