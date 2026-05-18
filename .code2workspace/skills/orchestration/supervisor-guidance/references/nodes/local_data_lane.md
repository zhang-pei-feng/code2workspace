# Local Data Lane Guidance

- Focus on structured local data, APIs, registries, or databases relevant to the report topic.
- Split the lane into `existing_data` and `computed_data`:
  - `existing_data` means already materialized local database rows, registries, APIs, prior orchestration artifacts, cached run outputs, or directly relevant history records.
  - `computed_data` means the requested value is not available yet and must be produced by selecting a compatible local operator plus dataset/input bundle, running it, and recording the new result.
- Use the local operator store as the primary path for computed evidence. Inspect operator stores, compatible datasets/input bundles, prior orchestration artifacts, and only directly relevant reusable calculation records.
- Benchmark comparison history is optional `existing_data`; it can support claims about prior tool behavior, datasets, input bundles, metrics, success/failure status, runtime artifacts, reproducibility, and evidence gaps, but it should not distract from running the needed operator when the task asks for new computed data.
- If the report requires prediction, simulation, scoring, metric computation, or other calculated evidence, use the local operator store as the operator library. Retrieve candidate operators and compatible datasets/input bundles, inspect the operator runtime fields, run the concrete WDL/Docker/entrypoint path when available, and cite the command, inputs, outputs, status, metrics, and artifact paths.
- Keep benchmark-history evidence separate from external surveillance/literature evidence; cite the record path, run id, dataset key, operator/tool name, success status, metrics, and artifact paths when used.
- Minimum output is:
  - one lane brief
  - concrete `existing_data` extracts or an explicit null-result statement
  - concrete `computed_data` outputs or an explicit no-compatible-operator/dataset statement
  - benchmark-history extracts or an explicit no-relevant-benchmark-history statement
  - data quality caveats
  - uncertainty note
- If no suitable local dataset is available, say so explicitly and return `partial` rather than continuing to search indefinitely.
- As soon as the minimum lane brief exists, stop and return structured JSON.
