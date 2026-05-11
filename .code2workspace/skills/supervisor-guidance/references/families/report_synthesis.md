# Report Family Guidance

- The report pipeline should preserve a formal structure: initialization, evidence-lane gathering, composition, and closeout.
- Initialization may spend time producing a robust report contract and scaffold if that reduces ambiguity for later lanes, but it must still terminate once the scaffold is usable.
- Always separate evidence, inference, and uncertainty in downstream report artifacts.
- Lane and composition nodes should inspect the run directory and consume the latest initialization/lane artifacts before expanding scope.
- For latest, recent, monitoring, or trend-sensitive report tasks, establish the current time window explicitly before drawing conclusions.
- Prefer absolute dates and date ranges in report artifacts instead of relying only on words like today, this week, or recently.
- If freshness materially affects the answer, verify the newest available source timestamps and state when the evidence was last updated.
