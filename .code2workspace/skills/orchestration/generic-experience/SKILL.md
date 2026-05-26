---
name: generic-experience
description: Harness-written generic orchestration experience memory. Stores accepted case abstractions, trajectories, and observed effects, then distills them into reusable planning hints for generic Supervisor Graph orchestration.
---

# Generic Experience

This skill package is runtime-owned.

It complements `supervisor-guidance`:

- `supervisor-guidance` holds the stable, hand-maintained generic orchestration rules
- `generic-experience` holds harness-generated experience distilled from accepted
  generic cases

## Storage Shape

The package has one append-friendly experience table plus detailed instance
records:

- `experience_table.json` is the runtime-facing table:
  classification, problem abstraction, explain, and instance paths
- `records/*.json` are the detailed per-case records used as provenance
- `generated/generic_orchestration_experience.md` is rebuilt from the table for
  compact prompt injection

Each detailed experience record should preserve problem classification,
problem abstraction, problem instance, trajectory, trajectory explain,
trajectory effect, applicability, and confidence.

## Runtime Contract

- generic runtime reads `experience_table.json` first, then uses matching
  `records/*.json` entries only as supporting examples
- if the table is absent, runtime may build an in-memory fallback table from
  `records/*.json`
- distilled reusable guidance lives under
  `generated/generic_orchestration_experience.md`
- experience hints must guide orchestration shape and evidence strategy only;
  they must not hard-code user answers

## Harness Contract

- only accepted or otherwise high-confidence generic harness outcomes should be
  written into this skill
- ordinary accepted cases may only append instance paths to the matching table
  row, or create a new row when no same-class row exists
- classification, problem abstraction, and explain may be rewritten only during
  periodic major table updates
- every 20 pending instances should trigger the deterministic major update hook
  to dedupe, sort, correct counts, and reset the pending counter
- new accepted cases should update `experience_table.json` and rebuild the
  distilled guidance artifact so future generic runs benefit automatically
