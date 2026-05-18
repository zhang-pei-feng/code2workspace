# Generic Harness Evaluation Plan

本文记录 generic 编排能力优化的实现方案。目标不是替代原始
`orchestration_runs` trace，而是把 verbose trace 压缩成 harness 可以比较、
排序、回归的结构化评价。

## 背景

generic 任务现在已经默认写入完整执行轨迹：

- `request.json`
- `task_classification.json`
- `retrieved_cases.json`
- `graph_round_*.json`
- `node_traces/*.json`
- `worker_outputs/*.json`
- `tool_activity.jsonl`
- `raw_worker_traces/*.jsonl`
- `final_response.md`
- `final_decision.json`

这些文件足够支撑人工审计，但 harness 优化需要更紧凑的指标：图形状、节点状态、
工具调用、原始 worker trace 覆盖率、耗时、来源 URL、答案是否保留证据边界等。

## Artifact Contract

generic run finalization now writes two evaluation artifacts:

- `evaluation.json`
  - keeps the shared supervisor evaluation envelope
  - uses generic-specific completion levels `D0-D6`
  - includes `generic_scores`, `generic_metrics`, and `generic_findings`
- `generic_trace_summary.json`
  - compact harness-facing summary extracted from the same evaluator result
  - intended as the first input for prompt/capability/graph-shape optimization

## Completion Levels

- `D0.no_generic_artifacts`: no usable generic artifacts
- `D1.classified_generic`: task classification or final decision marks generic
- `D2.graph_planned`: at least one `graph_round_*.json` contains nodes
- `D3.nodes_executed`: worker output exists for at least one node
- `D4.worker_trace_available`: `raw_worker_traces` or `tool_activity` exists
- `D5.final_answer_written`: `final_response.md` has user-facing content
- `D6.evidence_boundary_preserved`: final answer preserves an evidence boundary
  or audit summary signal

## Metrics

The first implementation computes only deterministic artifact metrics:

- routing and graph shape:
  - `classified_generic`
  - `round_count`
  - `node_count`
  - `edge_count`
  - `graph_shapes`
  - `graph_shape_label`
- execution state:
  - `executed_node_count`
  - `status_counts`
  - `failed_nodes`
  - `blocked_nodes`
  - `partial_nodes`
- trace coverage:
  - `raw_trace_file_count`
  - `raw_worker_message_count`
  - `raw_output_record_count`
  - `tool_event_counts`
  - `unknown_tool_events`
- harness cost signals:
  - `duration_by_node`
  - `total_duration_seconds`
  - `tool_event_count`
- evidence/answer signals:
  - `source_url_count`
  - `source_urls`
  - `has_fetch_after_search`
  - `final_answer_length`
  - `has_evidence_boundary`
  - `has_audit_summary`

## Scores

The evaluator emits six bounded `0-100` scores:

- `routing_score`
- `graph_fit_score`
- `traceability_score`
- `evidence_score`
- `answer_score`
- `efficiency_score`

These are deliberately simple rule scores. They are meant to support the first
harness ranking pass, not to be a final quality oracle.

## Current Limitations

- Evidence quality is still inferred from artifacts and final-answer signals,
  not judged semantically by a separate LLM.
- `source_urls` are extracted heuristically from messages and worker results;
  they are useful for triage but not yet a clean citation set.
- `unknown_tool_events` remain a trace-quality issue in `tool_activity.jsonl`
  and should be normalized in a later pass.
- The evaluator does not yet compare expected graph shape against a curated
  case label; the first version only describes the observed shape.

## Harness Usage

The intended first optimization loop is:

1. Run generic cases with one candidate prompt/guidance configuration.
2. Collect each run's `generic_trace_summary.json`.
3. Compare score distributions and findings across cases.
4. Inspect raw traces only for cases with low scores or surprising findings.
5. Change one guidance/prompt surface.
6. Repeat and compare summaries.

This gives generic orchestration a compact feedback loop while preserving the
full trace for audit and thesis evidence.
