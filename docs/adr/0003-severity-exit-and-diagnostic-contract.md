# ADR-003: Severity, exit codes, and the ORB / INPUT identity split

- Status: accepted
- Reconstructed: 2026-09-08
- Origin: Roadmap "Phase 3 — exit code"; implemented and verified in Phase 3-1
  / Redmine #5376, under Phase 3 / #5380
- Recorded by: Phase 3-0-1 / Redmine #5385
- Authoritative detail: `docs/failure-model.md`

## Note on reconstruction

This ADR was reconstructed after the decision had already been implemented. It
records the current authoritative decision and does not claim that this file
existed at the original decision date. It is a decision record, not a second
specification: where this file and `docs/failure-model.md` could be read
differently, `docs/failure-model.md` and the tests win, and this file should be
corrected.

## Context

Through Phase 2 the CLI had one binary outcome: no findings meant exit `0`;
any finding meant exit `1`. Phase 3 introduces three things that do not fit a
binary outcome:

- a `.orb-lint.yml` that can be malformed;
- a lint input that exists but cannot be read;
- the possibility that orb-lint itself, or its environment, fails.

Treating all of these as "exit 1" would make a consumer unable to tell whether
their repository is wrong or the checker is. Treating a malformed config as a
rule finding would mean inventing a fake `ORB-xxx` for something that is not a
policy.

Phase 2 had also established that lint evaluation, measurement, and enforcement
are separate responsibilities, and that a measurement failure must never become
a lint result. Any failure model had to keep that.

## Decision

### Exit codes

| exit | meaning |
|---|---|
| `0` | no violation, or warning-severity findings only |
| `1` | the repository under inspection is at fault |
| `2` | orb-lint itself, or its environment, could not complete the run |

Exit `1` covers an error-severity `ORB-xxx` finding, an unreadable lint input,
and an unreadable or invalid `.orb-lint.yml`. Exit `2` is reserved for
statements about orb-lint, never about the repository; an unclassified
exception reaching the CLI is exit `2`.

### Identity namespaces

- `ORB-xxx` identifies a policy evaluation result produced by a rule.
- `INPUT-xxx` identifies a repository input or configuration problem.
- An operational failure is converted into neither. It produces no finding and
  no diagnostic, because it is not evidence about the repository.

The two namespaces are disjoint, and the separation is enforced by the type: a
`Diagnostic` refuses any identity outside `INPUT-` at construction. Message text
is never the identity (see ADR-002).

### Severity

`Severity` is `warning` or `error`. In Phase 3 it exists only to distinguish
"exit `0` with warnings" from "exit `1` with errors". Warning findings are still
printed; only the exit code differs. `ORB-001` keeps `error` severity so its
Phase 1 behavior is unchanged. Deciding which rules are `error` is Phase 5 work
and is not fixed here.

### Boundary with Phase 2

The exit code is computed from the lint result, never from the measurement
outcome. When a repository input failure prevents a rule from running, that
rule is recorded as **not evaluated** (the Phase 2 state), not as zero findings,
and the lint outcome is `incomplete`.

## Rationale

Three codes rather than two because the question a CI consumer asks is "is it
my repository, or is it the tool?" and no binary answer can distinguish them.
Merging exit `2` into exit `1` would report a checker defect as a consumer
defect; merging it into exit `0` would be a silent pass, which the Roadmap's
fail-closed requirement for orb-lint forbids.

A separate `INPUT-` namespace rather than reusing `ORB-` because a broken
config is not a policy violation. If `.orb-lint.yml` syntax errors were
reported as, say, `ORB-000`, then measurement would count them as a rule,
ignore entries could suppress them, and Phase 5 severity promotion would have
to decide what severity a syntax error has. None of those questions should
exist.

Operational failures get no identity at all because giving them one would put
them into structured output as if they were facts about the repository. They
are facts about the run.

Severity is introduced minimally because the Roadmap's promotion workflow
(warning first, measure, fix, promote in a batch) needs the distinction to
exist before Phase 5, but does not need any rule other than `ORB-001` to have a
severity yet.

## Consequences

- Consumers can branch on exit code in CI: `1` is actionable in the
  repository, `2` is a bug report against orb-lint.
- Phase 3-3 JSON output separates `findings` (`ORB-`) from `diagnostics`
  (`INPUT-`) as two collections; it never mixes them into one list.
- Adding a new `INPUT-xxx` diagnostic is an additive public contract change.
  Changing what an existing one means is not.
- A previously unhandled exception is now exit `2` instead of a raw traceback.
  This is the one Phase 2 behavior deliberately changed, and
  `tests/test_cli.py` records it.
- Ignore entries (ADR-004) can name `ORB-xxx` only. There is no way to ignore
  an `INPUT-xxx` diagnostic; a broken config is fixed, not suppressed.
