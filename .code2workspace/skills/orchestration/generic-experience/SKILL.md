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

## Record Shape

Each experience record should preserve:

- problem classification
- problem abstraction
- problem instance
- trajectory
- trajectory explain
- trajectory effect
- applicability
- confidence

## Runtime Contract

- records live under `records/*.json`
- distilled reusable guidance lives under
  `generated/generic_orchestration_experience.md`
- generic runtime may retrieve both the distilled guidance and top matching
  records as planning hints
- experience hints must guide orchestration shape and evidence strategy only;
  they must not hard-code user answers

## Harness Contract

- only accepted or otherwise high-confidence generic harness outcomes should be
  written into this skill
- new accepted cases should rebuild the distilled guidance artifact so future
  generic runs benefit automatically
