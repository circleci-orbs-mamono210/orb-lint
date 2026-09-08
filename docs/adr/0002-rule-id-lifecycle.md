# ADR-002: Rule ID lifecycle

- Status: accepted
- Reconstructed: 2026-09-08
- Origin: Roadmap "ADR 一覧" and "Phase 7 — 固定するもの"; stable identity
  implemented in Phase 2-1 / Redmine #5350 and Phase 2-2 / #5351, under
  Phase 2 / #5349
- Recorded by: Phase 3-0-1 / Redmine #5385, under Phase 3 / #5380

## Note on reconstruction

This ADR was reconstructed after the decision had already been implemented. It
records the current authoritative decision and does not claim that this file
existed at the original decision date.

Two parts of this record have different kinds of evidence, and they are kept
apart below:

- The **identity** rules are implemented and regression-tested
  (`docs/measurement-contract.md`, `tests/`).
- The **lifecycle** rule (no reuse of a retired ID) is a Roadmap decision. With
  only `ORB-001` in existence it has not yet been exercised, so its evidence is
  the Roadmap text and nothing else.

## Context

Findings, measurement counts, ignore entries in `.orb-lint.yml`, and the
Phase 3-3 JSON output all need a way to say *which rule* they are about. The
obvious alternatives were the rule's message text or the Python symbol that
implements it. Both change for reasons unrelated to the policy: wording gets
edited, modules get renamed.

## Decision

- Every rule has a stable machine identity in the `ORB-` namespace.
  `ORB-001` is the currently implemented rule.
- The exact allocation strategy and numeric width for future rule IDs are not
  fixed by this ADR.
- Once a rule ID has been published, it is permanently bound to that rule.
- A retired ID must never be assigned to a different rule.
- A new rule must use an ID that has never previously been assigned.

The identity is the aggregation key for measurement and the reference key for
ignore entries and structured output. The human-readable `message`, the `path`,
and the `line` are diagnostic data, not identity: editing wording does not
create a new rule, and several findings for one rule in one execution belong to
the same rule result. `ORB-xxx` is disjoint from `INPUT-xxx` (see ADR-003).

## Rationale

For identity, the Phase 2 Measurement Contract states the reason directly: a
count keyed by message text would change every time someone improved the
wording, which would make measurement over time meaningless. Keying by a
dedicated ID makes wording a free change.

For lifecycle, the reason is the same one seen from the other side. An ignore
entry `rule: ORB-017` in a consumer repository, or a measurement snapshot that
says `ORB-017: 3`, records a fact about a specific policy. If `ORB-017` were
later reused for a different policy, that consumer would be silently ignoring a
rule it never meant to, and the snapshot would be comparing unrelated things.
Leaving a gap in the numbering costs nothing.

## Consequences

- Rule ID is a public contract from the moment a release carries it. Renaming
  a rule's ID is a breaking change; changing its message is not.
- Removing a rule leaves a permanent gap, and that is intended. A retired ID
  may be listed as retired in documentation, but its number is not available.
- Adding a rule in a later Phase includes choosing an ID that has never been
  assigned; how that ID is chosen is left to that Phase.
- The Phase 3-3 JSON schema and the Phase 7 stable contract can rely on
  `ORB-xxx` as a durable key without a second identifier.
