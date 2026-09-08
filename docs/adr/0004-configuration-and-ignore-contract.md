# ADR-004: Configuration ownership and ignore path matching

- Status: accepted; the "Ownership" decision was amended on 2026-09-08 (see
  "Amendments" at the end)
- Date: 2026-09-08
- Origin: Phase 3-2 / Redmine #5377, under Phase 3 / #5380
- Amended by: Phase 3-2-1 / Redmine #5384

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

> Amended by #5384: the module is now private. The text below is the original
> decision, kept for traceability; the current position is under "Amendments".

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

## Amendments

### 2026-09-08 — Phase 3-2-1 / #5384

Four points were settled before the Phase 3-3 JSON contract is defined on top
of this one. Nothing about path matching, expiry, or multiple-match attribution
changed.

#### 1. Ownership: the implementation is private

**Original decision.** `orb_lint/configuration.py` is public and deliberately
carries no leading underscore, so that `orb-lint-audit` can import it.

**Amended decision.** The module is renamed `orb_lint/_configuration.py`. It
remains the single authoritative implementation, and audit must still never
reimplement its semantics. But its module path, classes, and functions are not
a stable public Python API. The public contract is the meaning of
`.orb-lint.yml`, documented in `docs/configuration-contract.md`. When
`orb-lint-audit` exists and its needs are known, Phase 6 will define the
narrow public facade it requires on top of this module.

**Why the change.** The original decision conflated two things: "there is one
authoritative implementation" and "that implementation is a stable API". The
first is the architecture boundary the Roadmap requires. The second is a
compatibility promise about specific Python symbols, made before any consumer
exists to say which symbols it needs. Making the promise now would freeze
`Configuration`, `IgnoreRule`, and `load_configuration` as they happen to be
today; making it in Phase 6, against a real consumer, freezes only what is
actually used. Reversing a public-to-private change after audit has started
importing the module would be harder than doing it now, which is why the
amendment is made in Phase 3 rather than deferred.

#### 2. Path: exact match is a compatibility boundary

The original decision already chose exact matching and noted that globs could
be added later as an additive change. What was left implicit is now explicit:
adding pattern matching must never change the meaning of the existing `path`
field. If it is needed, it will be a separately named field.

To keep that door open, `path` now rejects the characters `*`, `?`, and `[`
with `INPUT-002`. Previously a validator would have accepted `src/*.yml` as a
literal filename; had any repository done that, a later pattern field could
not have been introduced without asking whether such entries meant the literal
or the pattern.

#### 3. Ignored findings are reported, not hidden

The original implementation recorded ignored findings on the execution result
but printed nothing for them, so an ignored-only repository produced the same
stdout as a clean one. That contradicted the boundary this ADR already stated:
an ignore suppresses enforcement, it does not erase the finding.

Every finding is now printed. An ignored one is followed by `ignored: <reason>`
and, when present, `expires: <date>`. The `orb-lint: OK` line carries an
ignored count when the count is nonzero, and is byte-identical to Phase 2 when
it is zero. Exit codes are unchanged. The exact format is in
`docs/configuration-contract.md`. Whether the JSON output carries the reason
and expiry as fields is a Phase 3-3 decision and is not fixed here.

#### 4. PyYAML dependency policy

The original "Consequences" noted that PyYAML becomes a runtime dependency.
The version range is now `PyYAML>=6.0,<7`: the lower bound is what the code
uses, the upper bound is what CI verifies. Determinism across installs matters
more than picking up an untested major automatically. Raising the bound is a
deliberate change accompanied by a passing test run. No YAML parser is written
in-house; that would create exactly the second interpretation this ADR exists
to prevent.
