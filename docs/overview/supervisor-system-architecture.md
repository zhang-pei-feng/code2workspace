# Supervisor System Architecture

This document captures the current supervisor-first architecture after the
runtime was generalized so every task enters the supervisor layer and node
experience is increasingly stored as Skill assets rather than embedded directly
in Python prompt branches.

## Overview

```mermaid
flowchart TD
    U[User Task<br/>CLI / TUI / Non-interactive] --> A[create_cli_agent]
    A --> B[base_agent<br/>workspace agent]
    A --> C[supervisor wrapper graph]

    C --> D[route]
    D -->|task exists| E[supervise]
    D -->|no task| F[fallback]
    F --> B

    E --> G[run_supervisor_orchestration]
    G --> H[SQLiteCaseIndex rebuild/search]
    H --> I[retrieved cases]
    I --> J[planner]

    J --> K[task classification]
    K --> L[guidance ids]
    K --> M[task type]

    L --> N[graph skeleton + metadata]
    M --> N
    N --> O[TaskGraph]
    O --> P[execute_graph_round]

    P --> Q[ready-node scheduler]
    Q --> R[generic worker invocations]

    R --> S[capability registry]
    R --> T[node guidance assets<br/>Skill layer]
    S --> U2[tool surface hints]
    T --> V[node strategy hints]

    U2 --> W[worker prompt assembly]
    V --> W
    W --> X[base_agent.ainvoke]
    X --> Y[WorkerResult]

    Y --> Z[node_traces / worker_outputs / tool_activity]
    Z --> AA[TaskExecutionRound]
    AA --> AB[SupervisorDecision]
    AB -->|replan| J
    AB -->|stop| AC[final_summary / final_decision]
```

## Layer Split

- `libs/code2workspace/code2workspace/orchestration_runtime.py`
  graph data model, task classification, family guidance ids, graph skeleton
  planning, and dependency-aware execution
- `libs/cli/code2workspace_cli/supervisor_runtime.py`
  CLI wrapper graph, artifact persistence, case retrieval, worker invocation,
  and worker prompt assembly
- `libs/cli/code2workspace_cli/supervisor_capabilities.py`
  capability-to-tool registry plus node-guidance asset loading
- `.code2workspace/skills/supervisor-guidance/`
  node execution strategy and experience fragments used by the worker prompt

## Current Execution Model

- Every task now enters supervisor first.
- Unknown tasks use a generic graph:
  - `init_generic`
  - `worker_context`
  - `worker_solution`
  - `compose_generic`
  - `summarize`
- Thesis-facing known task families currently add guidance/template skeletons:
  - `benchmark`
  - `github2workspace`
- Capability bundles remain code-level execution contracts.
- Node experience and strategy are moving into Skill assets.

## Artifact Contract

Canonical supervised runs write under:

- `<thread_workspace>/orchestration_runs/<run_id>/`

Expected artifacts:

- `request.json`
- `retrieved_cases.json`
- `graph_round_*.json`
- `node_traces/*.json`
- `worker_outputs/*.json`
- `tool_activity.jsonl`
- `final_summary.md`
- `final_decision.json`

The SQLite case index remains rebuildable cache only; the run directories are
the canonical source of truth.
