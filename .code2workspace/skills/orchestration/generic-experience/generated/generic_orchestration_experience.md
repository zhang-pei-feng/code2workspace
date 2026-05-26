# Generic Orchestration Experience

- Use these distilled experience patterns as planning hints, not as hard-coded answers.
- Match graph size to the task; prefer the smallest graph that still protects evidence quality and answer usefulness.
- Reuse a recorded trajectory only when its applicability and constraints match the current task.

## local_code_explanation__local_only__repo_local__da84aafd

- Classification: local_code_explanation__local_only__repo_local
- Problem abstraction: Explain repo-local runtime or artifact behavior from local code and keep the answer compact.
- Explain: Strategy: use one bounded repo-inspection lane to find the exact code paths or run artifacts that answer the question, then do a single synthesis pass. Keep evidence local; stop once the necessary repository files, tests, or orchestration artifacts have been read, and avoid web discovery or report-style expansion unless the user asks for it. Observed successful shape: evidence_then_synthesis with about 3 nodes; prefer init -> one evidence worker -> summarize/final response instead of parallel lanes. Because the prompt asks for a compact answer, put the conclusion first and include only the minimum evidence boundary needed to make the claim auditable. Risk control: observed evidence scores were sometimes weak, so explicitly cite the specific artifacts used and avoid overclaiming; local-only tasks should not invent or rely on external source URLs; watch for over-orchestration when the user only wants a short local answer.
- Instance count: 4
- Example instance paths: .code2workspace/skills/orchestration/generic-experience/records/generic-eval-scores-train__iter-001__1d00fa96b2.json, .code2workspace/skills/orchestration/generic-experience/records/generic-trace-artifacts-train__iter-001__241ade8dac.json, .code2workspace/skills/orchestration/generic-experience/records/generic-trace-vs-tool-activity-holdout__iter-001__5507587dfc.json

## evidence_judgment__local_only__repo_local__dc0746e4

- Classification: evidence_judgment__local_only__repo_local
- Problem abstraction: Give a bounded judgment with explicit evidence boundaries and no unnecessary report structure.
- Explain: Strategy: frame the task as a bounded repo-local judgment: inspect only the artifacts needed to support or reject the claim, then state the decision and its limits. Keep evidence local; stop once the necessary repository files, tests, or orchestration artifacts have been read, and avoid web discovery or report-style expansion unless the user asks for it. Observed successful shape: evidence_then_synthesis with about 3 nodes; prefer init -> one evidence worker -> summarize/final response instead of parallel lanes. Because the prompt asks for a compact answer, put the conclusion first and include only the minimum evidence boundary needed to make the claim auditable. Risk control: observed evidence scores were sometimes weak, so explicitly cite the specific artifacts used and avoid overclaiming; watch for over-orchestration when the user only wants a short local answer.
- Instance count: 1
- Example instance paths: .code2workspace/skills/orchestration/generic-experience/records/generic-optimization-gap-train__iter-001__7b75c9f4a9.json
