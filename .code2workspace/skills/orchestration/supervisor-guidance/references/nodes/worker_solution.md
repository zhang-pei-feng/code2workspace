# Generic Worker Solution Guidance

- Focus on implementation, execution, repair, calculation, or solution design needed for the generic task.
- Start from the specific blocker, decision, or computed value that the final answer actually needs; do not widen the task just because more tools are available.
- Reuse local files, prior worker evidence, and concrete runtime artifacts before exploring new branches.
- When the solution depends on evidence gathered elsewhere, read only the exact worker outputs or artifacts needed to complete the answer or repair.
- Stop when the worker has enough concrete material for `compose_generic`; avoid extra tool loops once the answer path is already supported.
