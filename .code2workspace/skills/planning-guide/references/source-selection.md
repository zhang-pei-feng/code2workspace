# Source Selection Heuristics

Choose sources by what the task needs to prove, not by habit.

## General rule

Prefer the cheapest authoritative source that can answer the question with
enough confidence.

## Data and integration tasks

Prefer local evidence before external lookup.

Look at:

- database schemas and migrations
- local databases or query layers
- snapshots, exported datasets, and cached responses
- ETL outputs and transformation code
- API contracts and interface docs

Use external sources when you need current upstream behavior, live schema
changes, or authoritative service documentation.

## Monitoring, research, and report tasks

Decide first whether the task needs historical context, current status, or both.

Common source classes:

- official documentation and official monitoring sites
- project-local snapshots, stored reports, or curated tables
- papers, preprints, and technical reports
- current web sources when freshness materially changes the answer

When freshness matters, prefer official or primary sources over summaries.

## Code and repository tasks

Start locally unless the task explicitly needs fresh external information.

Look at:

- source code and nearby modules
- tests and snapshots
- configs, schemas, and manifests
- entrypoints and task runners
- logs, tracebacks, and prior outputs

Use external docs only when local code or errors point to an API, library, or
tool behavior that is not reliably inferable from the repository.

## Local vs external evidence

Ask these questions before searching externally:

- Can this fact be verified from the repository or local environment?
- Is the needed information temporal or likely to have changed recently?
- Does the answer require authority that local materials cannot provide?
- Is the cost of being wrong high enough to justify external verification?
