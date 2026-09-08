## Failure Model / Exit Code Contract

This document defines the public failure semantics of the `orb-lint` CLI: which
exit code a run produces, and which identity namespace classifies a failure that
is not a rule finding.

Origin: Phase 3-1 / Redmine #5376, under Phase 3 / #5380.
Related work: configuration and ignore semantics are Phase 3-2 / #5377;
serialization is Phase 3-3 / #5378 (`docs/adr/0014-json-schema-v1.md`);
integration verification is Phase 3-4 / #5379
(`docs/phase-3-4-verification.md`).
Repository location: `docs/failure-model.md`.

### Exit codes

| exit | meaning |
|---|---|
| `0` | no violation, or warning-severity findings only |
| `1` | the repository under inspection is at fault |
| `2` | orb-lint itself, or its environment, could not complete the run |

Exit `1` covers three distinct repository-side conditions:

- an error-severity `ORB-xxx` violation;
- a lint input that exists but cannot be read or decoded;
- an `.orb-lint.yml` that exists but cannot be read, decoded, or validated.

Exit `2` is reserved for statements about orb-lint, not about the repository.
An unclassified exception reaching the CLI is exit `2`, never exit `1`: a defect
in the checker must not be reported as a defect in the consumer.

### Identity namespaces

Two namespaces are kept disjoint:

- `ORB-xxx` identifies a policy evaluation result produced by a rule.
- `INPUT-xxx` identifies a repository input or configuration problem.

A `Diagnostic` rejects any identity outside the `INPUT-` namespace at
construction, so the separation is enforced by the type rather than by
convention. Message text is never the identity.

Currently defined diagnostics:

| identity | condition |
|---|---|
| `INPUT-001` | a targeted lint input cannot be read or decoded |
| `INPUT-002` | `.orb-lint.yml` cannot be read, decoded, or validated |

An operational failure is converted into neither namespace. It is not evidence
about the repository, so it produces no finding and no diagnostic.

### Severity

`Severity` is `warning` or `error`. It exists in this Phase only to separate
"exit `0` with warnings" from "exit `1` with errors". `ORB-001` keeps `error`
severity, so its Phase 1 exit-`1` behavior is unchanged. Promoting or demoting
rules is Phase 5 work, not this Phase's.

Warning-severity findings are still printed. Only the exit code differs.

### Output streams

The rules below describe the default `--format text`. With `--format json`
(Phase 3-3 / #5378, ADR-014) stdout carries exactly one JSON document and
nothing else; diagnostics and operational failures still go to stderr, and on
exit `2` stdout is empty. Exit codes are identical in both formats.

- Findings are printed to stdout, in the existing
  `path:line: RULE-ID: message` format. An ignored finding is printed too,
  followed by indented `ignored:` / `expires:` lines; see
  `docs/configuration-contract.md`.
- Diagnostics are printed to stderr, as `path: INPUT-ID: message`.
- Operational failures are printed to stderr and identify the failing exception
  class.
- `orb-lint: OK` is printed only when there is neither an active finding nor
  a diagnostic, so the clean-repository output is byte-identical to Phase 2.
  When the only findings are ignored ones, the line gains a count:
  `orb-lint: OK (N ignored finding[s])`.

### Boundary with Phase 2

The measurement outcome is deliberately not consulted when computing the exit
code. A measurement failure does not change the repository-facing result, which
preserves the Phase 2 separation between lint evaluation, measurement, and
enforcement.

When a repository input failure prevents evaluation, the affected rule is
recorded as **not evaluated** rather than as zero findings, and the lint outcome
is `incomplete`. This reuses the Phase 2 distinction instead of introducing a
second one.

### Deliberate change to a Phase 2 behavior

Before this Phase, an unclassified exception escaping evaluation propagated out
of `main()` as an unhandled traceback. It is now caught and reported as exit
`2`. The original guarantee is preserved — such an error is still never reported
as a clean repository — and `tests/test_cli.py` records the change explicitly.

### Not in this Phase

- JSON serialization and its schema (Phase 3-3);
- GitHub or CircleCI API access, required checks, and audit state;
- promoting rules to error severity for enforcement (Phase 5);
- auto-fix.

`orb_lint/_configuration.py` (private) owns the authoritative interpretation
of `.orb-lint.yml`, including its schema and semantic validation. Every
rejection it makes surfaces as `INPUT-002`. See `docs/configuration-contract.md`.
