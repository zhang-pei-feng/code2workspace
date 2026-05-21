# Computed Data Lane Guidance

- Focus only on report evidence that needs new local computation.
- First state why existing_data is insufficient for the needed report claim or metric.
- Search operator_store for a compatible operator and dataset_store for a compatible dataset/input bundle before falling back to operator hints or old benchmark records.
- Do not run an operator just because candidates exist; run only when the requested report value needs computed_data.
- When computation is needed, inspect runtime fields, run the concrete WDL/Docker/entrypoint path when available, and record command, inputs, outputs, status, metrics, and artifact paths.
- If no compatible operator or dataset exists, return `partial` with a concrete no-compatible-operator/dataset statement instead of broad searching.
- Minimum output is one lane brief, the existing-data insufficiency reason, selected operator/dataset rationale or compatibility blocker, result artifacts when run, data quality caveats, and an uncertainty note.
- As soon as the minimum lane brief exists, stop and return structured JSON.
