# complex-qa-suite-v1

`complex-qa-suite-v1` is the first versioned dataset for the complex-QA benchmark
described in
`docs/superpowers/specs/2026-04-23-complex-qa-benchmark-design.md`.

It contains exactly 12 cases and is intentionally scoped to the dataset and
content layer only:

- versioned case files under `experiments/skill_tests/cases/complex_qa/`
- a machine-readable catalog in `catalog.json`
- a fixed batch manifest in `experiments/skill_tests/batches/complex-qa-suite-v1.md`

## Scope

The suite covers six task families from the design:

- `trend_analysis`
- `database_lookup`
- `literature_search`
- `cross_source_synthesis`
- `report_generation`
- implicit risk judgment embedded in the synthesis/report cases

The 12 selected cases were chosen because together they stress the main failure
modes already observed in the repo's complex monitoring questions:

- recency-sensitive trend reading
- lineage or mutation lookup without hallucinating unsupported fields
- literature and clinical-trial retrieval for narrow variant questions
- cross-source synthesis where official monitoring, mutation data, and papers
  must be reconciled
- integrated risk judgment with explicit uncertainty handling
- report-style output that still needs evidence discipline

## Why These 12

The case list mixes three sources of value:

- Repacked prior measured questions:
  cases 1, 2, 7, 9, and 11 come directly from the earlier
  `covid-monitoring-*` batch so the new suite can rerun them under one versioned
  benchmark instead of treating old results as the main baseline.
- Adjacent follow-on questions:
  cases 4, 5, and 6 reuse nearby monitoring or variation-query capabilities but
  tighten the benchmark on explicit share, mutation, and immunity-barrier
  judgments.
- New synthesis/report stress tests:
  cases 3, 8, 10, and 12 are the higher-ambiguity prompts where planning,
  source selection, and uncertainty calibration matter most.

## Fixed Split Suggestion

The suite keeps a fixed 8/4 suggestion rather than sampling at runtime.

- Train (8): cases 1, 2, 4, 5, 6, 7, 9, 11
- Holdout (4): cases 3, 8, 10, 12

This split keeps the train side broad across monitoring, lookup, and moderate
cross-source synthesis while reserving the more open-ended convergence,
latest-product, integrated immune-escape, and WHO-style report tasks for
holdout.

## Notes

- The case metadata intentionally keeps `expected_behaviors` and
  `expected_outputs` minimal for now so v1 does not create brittle pass/fail
  assertions before the dedicated judge layer lands.
- `prior_case_refs` point to earlier measured cases when there is clear reuse,
  but the suite should still be rerun from scratch as its own benchmark.
