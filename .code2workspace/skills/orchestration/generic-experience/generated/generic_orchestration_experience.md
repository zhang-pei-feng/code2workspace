# Generic Orchestration Experience

- Use these distilled experience patterns as planning hints, not as hard-coded answers.
- Match graph size to the task; prefer the smallest graph that still protects evidence quality and answer usefulness.
- Reuse a recorded trajectory only when its applicability and constraints match the current task.

## generic-eval-scores-train__iter-001__1d00fa96b2

- Applies to: Explain repo-local runtime or artifact behavior from local code and keep the answer compact.
- Preferred trajectory: evidence_then_synthesis; nodes=n/a; stop rule=stop after enough source-backed evidence exists for one bounded synthesis pass
- Why it worked: This trajectory kept the graph small enough for the task while still leaving a clear synthesis step. It fits local-only questions because it can stop after the needed repo artifacts are read. The resulting answer kept evidence provenance visible.
- Use when: the user wants a repo-local explanation or decision and one bounded evidence lane is enough
- Avoid when: the task explicitly needs broad web discovery, monitoring, or a formal report artifact
- Observed effect: case_score=90.8, delta_vs_previous=+1.4, evidence_score=80.0, efficiency_score=100.0, traceability_score=100.0

## generic-trace-vs-tool-activity-holdout__iter-001__5507587dfc

- Applies to: Explain repo-local runtime or artifact behavior from local code and keep the answer compact.
- Preferred trajectory: evidence_then_synthesis; nodes=n/a; stop rule=stop after enough source-backed evidence exists for one bounded synthesis pass
- Why it worked: This trajectory kept the graph small enough for the task while still leaving a clear synthesis step. It fits local-only questions because it can stop after the needed repo artifacts are read. The resulting answer kept evidence provenance visible.
- Use when: the user wants a repo-local explanation or decision and one bounded evidence lane is enough
- Avoid when: the task explicitly needs broad web discovery, monitoring, or a formal report artifact
- Observed effect: case_score=88.3, delta_vs_previous=+2.1, evidence_score=80.0, efficiency_score=85.0, traceability_score=100.0

## generic-unknown-tool-fix-holdout__iter-001__579ec7a0d1

- Applies to: Explain repo-local runtime or artifact behavior from local code and keep the answer compact.
- Preferred trajectory: evidence_then_synthesis; nodes=n/a; stop rule=stop after enough local artifacts are read for synthesis
- Why it worked: This trajectory kept the graph small enough for the task while still leaving a clear synthesis step. It fits local-only questions because it can stop after the needed repo artifacts are read.
- Use when: the user wants a repo-local explanation or decision and one bounded evidence lane is enough
- Avoid when: the task explicitly needs broad web discovery, monitoring, or a formal report artifact
- Observed effect: case_score=87.5, delta_vs_previous=+2.1, evidence_score=60.0, efficiency_score=100.0, traceability_score=100.0

## generic-optimization-gap-train__iter-001__7b75c9f4a9

- Applies to: Give a bounded judgment with explicit evidence boundaries and no unnecessary report structure.
- Preferred trajectory: evidence_then_synthesis; nodes=n/a; stop rule=stop after enough local artifacts are read for synthesis
- Why it worked: This trajectory kept the graph small enough for the task while still leaving a clear synthesis step. It fits local-only questions because it can stop after the needed repo artifacts are read.
- Use when: the user wants a repo-local explanation or decision and one bounded evidence lane is enough
- Avoid when: the task explicitly needs broad web discovery, monitoring, or a formal report artifact
- Observed effect: case_score=90.8, delta_vs_previous=+1.4, evidence_score=60.0, efficiency_score=100.0, traceability_score=100.0

## generic-trace-artifacts-train__iter-001__241ade8dac

- Applies to: Explain repo-local runtime or artifact behavior from local code and keep the answer compact.
- Preferred trajectory: evidence_then_synthesis; nodes=n/a; stop rule=stop after enough local artifacts are read for synthesis
- Why it worked: This trajectory kept the graph small enough for the task while still leaving a clear synthesis step. It fits local-only questions because it can stop after the needed repo artifacts are read.
- Use when: the user wants a repo-local explanation or decision and one bounded evidence lane is enough
- Avoid when: the task explicitly needs broad web discovery, monitoring, or a formal report artifact
- Observed effect: case_score=82.5, delta_vs_previous=+1.4, evidence_score=40.0, efficiency_score=100.0, traceability_score=100.0
