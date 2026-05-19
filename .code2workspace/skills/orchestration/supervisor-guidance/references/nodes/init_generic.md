# Generic Init Guidance

- Keep this node narrow: define the generic delivery contract, pick 1-3 bounded worker units, and record only the next execution batch.
- Prefer the smallest graph that can still answer the task with evidence. For a small local question, direct explanation, or one-lane evidence check, avoid splitting into redundant context and solution lanes.
- Use separate context and solution lanes only when the contextual evidence will materially change the downstream answer or implementation path.
- If the generic task needs prediction, simulation, scoring, or other computed evidence, plan one worker that searches `operator_store`, selects a compatible dataset or input bundle, and runs the chosen operator when the local runtime path is concrete enough.
- Stop once the worker split, evidence expectations, and compose target are concrete enough for the next round.
