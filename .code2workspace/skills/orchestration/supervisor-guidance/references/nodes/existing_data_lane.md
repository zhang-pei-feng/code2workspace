# Existing Data Lane Guidance

- Focus only on evidence that already exists locally: database rows, registries, APIs, dataset_store records, cached artifacts, prior orchestration outputs, and benchmark/history records.
- Do not run operators or create new computed outputs from this lane.
- Query the most relevant local stores first, then summarize concrete records and cite record paths, dataset ids, run ids, timestamps, and data quality caveats.
- If no relevant existing local data is available, return a clear null-result statement and identify the exact evidence gap a computed_data lane or composition would need to handle.
- Keep local evidence separate from monitoring and literature evidence.
- Minimum output is one lane brief, concrete extracts or a null-result statement, data quality caveats, and an uncertainty note.
- As soon as the minimum lane brief exists, stop and return structured JSON.
