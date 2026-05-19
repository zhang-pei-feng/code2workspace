# Generic Init Guidance

- Keep this node narrow: define the generic delivery contract, pick the next 1-3 bounded worker units, and record only the next execution batch.
- Prefer a serial evidence loop by default: gather the most relevant evidence first, judge whether it is enough, gather more only when the answer still has a concrete gap, then summarize once the evidence is sufficient.
- Prefer the smallest graph that can still answer the task with evidence. For a small local question, direct explanation, or one-lane evidence check, avoid splitting into redundant context and solution lanes.
- Use separate context and solution lanes only when the contextual evidence will materially change the downstream answer or implementation path; use parallel lanes only when the user explicitly asks for parallel work or when independent evidence branches are clearly necessary.
- If the generic task may need prediction, simulation, scoring, or other computed evidence, first plan for a judgment about whether existing local evidence is already sufficient. Only when a real evidence gap remains should you plan a worker that searches `operator_store`, selects a compatible dataset or input bundle, and runs the chosen operator when the local runtime path is concrete enough.
- Stop once the worker split, evidence expectations, and compose target are concrete enough for the next round.
