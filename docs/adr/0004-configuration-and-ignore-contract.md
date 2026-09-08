# ADR-004: Configuration ownership and ignore path matching

- Status: accepted
- Date: 2026-09-08
- Origin: Phase 3-2 / Redmine #5377, under Phase 3 / #5380

## Note on numbering

This repository had no `docs/adr/` directory before this decision. The Roadmap
refers to ADR-001 through ADR-003, but no such records exist here. The number
`0004` is kept because #5377 names it, and this file establishes the directory.
Whether the earlier records should be reconstructed or renumbered is left open.

Update (2026-09-08, Redmine #5385): ADR-001 through ADR-003 were reconstructed
from the Roadmap and the completed Phase 1–3 tickets, keeping this number.

## Context

Phase 3-2 makes `.orb-lint.yml` a public contract. Two questions had to be
settled rather than left to the implementation, because both are hard to change
once repositories depend on them:

1. who is allowed to interpret the file, given that a future `orb-lint-audit`
   will read the same file; and
2. what a `path`-scoped ignore actually matches.

The ticket also required that no unverified glob library be assumed.

## Decision

### Ownership

`orb_lint/configuration.py` is the single authoritative implementation, and it
is public. `orb-lint-audit` must import it rather than reimplement parsing,
validation, normalization, ignore matching, or expiry.

The module deliberately does not carry a leading underscore. A private name
would tell the audit author that importing it is unsupported, which is the
opposite of the boundary being established.

### Path matching

A `path`-scoped ignore matches an **exact, repository-root-relative POSIX
path**. Normalization strips whitespace and `.` segments. Absolute paths, `..`
segments, trailing slashes, and backslashes are rejected.

There is no glob or prefix matching.

### Expiry

`expires` is inclusive of the named day, evaluated in UTC, with no grace period.

### Multiple matches

A finding is ignored when at least one active entry matches. The first such
entry in file order is attributed. Expired entries never match.

## Rationale

Exact matching was chosen over globbing because it is unambiguous and because
the motivating case is narrow: exempting one development file, such as
`.circleci/test-deploy.yml`, while the same rule stays active in the production
config. Exact matching serves that case exactly.

Adding globs later is an additive change that can be made deliberately, with its
own decision record. Starting with globs would be the opposite: the semantics of
`*` across directory separators, of leading `**`, and of case sensitivity would
all become contract before anyone needed them, and narrowing them afterwards
would break repositories. It would also mean choosing a matching library now,
which #5377 explicitly ruled out.

Rejecting `..` and absolute paths follows from the target boundary established
in Phase 2: one execution inspects one repository. An ignore that could name a
path outside it would have no defined meaning.

Inclusive expiry was chosen because `expires: 2026-12-31` reads naturally as
"valid until the end of 2026", and the alternative silently shortens every
exception by a day. UTC was chosen so the same commit expires at the same moment
regardless of which region runs CI.

Attributing the first active match keeps the result deterministic without
inventing a specificity ranking between rule-level and path-scoped entries.
Ranking could be added later if a real case calls for it.

## Consequences

- `orb-lint-audit` gains a dependency on the `orb_lint` package. That is
  intended: one interpretation of the file, in one place.
- Repositories cannot exempt a directory in one entry. A directory-wide
  exception needs one entry per file, or a rule-level ignore.
- Adding glob support later is a public contract change and needs its own ADR.
- `PyYAML` becomes a runtime dependency of the CLI, since `.orb-lint.yml` is
  YAML and hand-parsing a subset would create exactly the second interpretation
  this decision exists to prevent.
