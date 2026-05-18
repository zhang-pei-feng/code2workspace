# Generic Worker Context Guidance

- For generic tasks that require current facts, monitoring, trend assessment, factual verification, source-backed judgment, or external evidence, use the same D2 default evidence depth as report monitoring lanes.
- D2 means targeted trusted-source search plus fetching/reading the concrete page, PDF, CSV, JSON, dashboard export, code artifact, or dataset needed to support the answer.
- Scope before depth: identify the topic, geography or repository boundary, time window, freshness requirement, and minimum source coverage before expanding the search.
- Use this source priority order unless the user says otherwise: user-specified sources, whitelisted official or primary sources, curated project skills/local stores/structured APIs, targeted trusted-domain search, then full-web search only for discovery or evidence-gap fallback.
- If the generic judgment requires prediction, simulation, scoring, metric calculation, or other computed evidence, treat local operator stores as the first local computation path before broad external discovery. Use benchmark comparison history only as optional existing evidence when directly relevant.
- Split local evidence into `existing_data` and `computed_data`: reuse already materialized local records when enough, but when the needed value is missing, retrieve a compatible operator and dataset/input bundle, run the concrete WDL/Docker/entrypoint path when available, and record the command, inputs, outputs, status, metrics, and artifact paths.
- If this worker was planned for local computation, search `operator_store` first, list candidate operators and dataset/input bundles, choose the best compatible operator, execute it when the runtime fields are sufficient, and return the computed output artifact as evidence.
- Escalate to D3 when the generic task asks for recent change, trends, watch items, monitoring status, or comparison across time.
- Escalate to D4 only when the task is high-stakes, highly uncertain, contested, or explicitly asks for comprehensive research.
- For casual explanation, local code inspection, or tasks whose evidence is already in the workspace, keep the depth at D0-D1 and avoid unnecessary browsing.
- Record source categories, dates or freshness when relevant, and whether each source directly supports the claim or only provides inferred/proxy context.
