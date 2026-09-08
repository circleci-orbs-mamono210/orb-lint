# ADR-014: JSON output schema v1

- Status: accepted
- Date: 2026-09-08
- Origin: Phase 3-3 / Redmine #5378, under Phase 3 / #5380
- Depends on: ADR-002 (rule identity), ADR-003 (exit codes, `ORB` / `INPUT`
  split), ADR-004 as amended by #5384 (ignore attribution)

## Context

The human-readable CLI output settled in #5376 and #5384 is for people reading
a CI log. Phase 4 deploys orb-lint to every Orb repository in report-only
mode, and later tooling (fleet aggregation, the Phase 6 audit's expiry
inventory) needs to read results without parsing prose. That requires a
machine-readable document with a stated shape.

Two shortcuts were rejected before designing one:

- Serializing the private measurement result. Its representation is an
  implementation detail of Phase 2 and changes when the implementation does;
  publishing it would make every internal change a compatibility event.
- Serializing the text output line by line. Its order is evaluation order,
  which is not a contract, and it carries no field boundaries.

## Decision

### Schema v1

```json
{
  "schema_version": 1,
  "tool_version": "<orb_lint.__version__>",
  "findings": [
    {
      "rule": "ORB-001",
      "severity": "error",
      "path": ".circleci/test-deploy.yml",
      "line": 8,
      "message": "...",
      "ignored": true,
      "ignore_reason": "development bootstrap only",
      "ignore_expires": "2026-12-31"
    }
  ],
  "diagnostics": [
    { "diagnostic": "INPUT-002", "path": ".orb-lint.yml", "message": "..." }
  ]
}
```

- `schema_version` is `1`. It is bumped only by a decision record. Additive
  fields do not bump it.
- `tool_version` is the runtime `orb_lint.__version__`, unmodified. Aligning
  it with the release version is release-gate work, not the serializer's.
- `findings` holds every `ORB-xxx` result, ignored or not. `diagnostics`
  holds every `INPUT-xxx` result. The two never mix.
- Every finding has the same eight keys. An active finding carries
  `ignored: false`, `ignore_reason: null`, `ignore_expires: null`; the shape
  does not vary with state, so consumers never branch on key presence.
- `ignore_reason` and `ignore_expires` come from the entry attributed by the
  first-active-match rule of ADR-004. `ignore_expires` is an ISO date string
  or null.
- A diagnostic's `path` is null when the problem is not about one file.
- An operational failure appears in neither collection (see below).

Until Phase 7, `schema_version: 1` is the public contract of v0.2.0, not a
stable compatibility guarantee.

### CLI: `--format text|json`

A format selector, defaulting to `text`, rather than a `--json` flag. Adding a
third format later is then a new choice, not a second flag whose interaction
with the first has to be defined. Only `text` and `json` exist in this Phase.

### stdout / stderr boundary

In JSON mode stdout carries exactly one JSON document and nothing else: no
finding lines, no `ignored:` / `expires:` lines, no `orb-lint: OK`. Diagnostics
and operational failures go to stderr in every format, as they already did.
A consumer may therefore parse stdout without filtering.

When a repository input diagnostic exists, JSON mode writes the document with
it in `diagnostics`, writes the human-readable diagnostic to stderr, and exits
`1`, exactly as text mode does apart from the stdout shape.

### Exit 2 emits no document

On an operational failure stdout is empty, stderr carries the existing
message, and the exit code is `2`. No document, not even an empty one.

The serializer builds and encodes the whole document before anything is
written, and the CLI writes it once. If encoding itself fails, that is an
operational failure like any other: stdout stays empty. A partial document is
never left behind.

### Deterministic ordering

`json.dumps(sort_keys=True)` fixes key order. Collection order is fixed by
sorting on every public field:

- findings by `(path, line, rule, severity, message, ignored,
  ignore_reason or "", ignore_expires or "")`;
- diagnostics by `(path or "", diagnostic, message)`.

Using every field, not just a prefix, is what makes the guarantee "same
semantic result, same bytes" rather than "usually the same". Two findings that
differ only in ignore metadata would otherwise fall back to evaluation order.

### Text mode is unchanged

Text mode keeps evaluation order and the #5384 contract. The JSON sort is not
applied to it. A formatter does not get to redesign the output people already
read.

### Serializer is private and separate

`orb_lint/_serialization.py` projects `_ExecutionResult` onto the schema. It
reads findings, ignore attribution, and diagnostics; it never reads the
measurement value. The module is private; the JSON document is the contract.

## Rationale

**Why include the ignore reason and expiry now.** #5384 established that an
ignore suppresses enforcement without erasing the finding, and put the reason
in the text output. A JSON consumer that could see `ignored: true` but not why
would have less information than a human reading the log, and the Phase 6
expiry inventory would have to re-parse `.orb-lint.yml` to recover the date.
Both fields are additive, so including them costs nothing in compatibility.

**Why a fixed shape with nulls.** Optional keys push a presence check into
every consumer and make "the key was absent" ambiguous between "not ignored"
and "old tool version". Nulls keep one shape per schema version.

**Why no document on exit 2.** An operational failure is a statement about
orb-lint, not about the repository (ADR-003). A document with empty
`findings` and `diagnostics` would read as a clean repository to any consumer
that did not also check the exit code. Emitting nothing is the only output
that cannot be misread.

**Why a separate `diagnostic` key rather than reusing `rule`.** The two
namespaces are disjoint by type (ADR-003). Giving them different key names in
the schema keeps that visible in the document itself, and stops a consumer from
accidentally treating an `INPUT-` identity as a rule to aggregate.

**Why `tool_version` is not pinned in tests.** The repository version and the
release version drift between releases by design. A test that asserts a
literal would fail on every bump for no reason; the contract is only that the
document reports what the installed package reports.

## Consequences

- Consumers can rely on: one document on stdout in JSON mode, stable key and
  element order, fixed finding shape, and an empty stdout meaning exit 2.
- Adding a field to a finding or diagnostic is an additive change: no schema
  bump, but a note in this ADR. Removing or renaming one is a bump.
- Phase 4 can snapshot JSON output per repository and diff it across runs,
  because identical semantic results produce identical bytes.
- Phase 6 can read `ignore_expires` directly from the JSON to build the expiry
  inventory, without owning a second `.orb-lint.yml` parser. It is not
  required to; the Roadmap keeps the parser available to it as well.
- Phase 7 decides whether this schema becomes the stable v1 guarantee or is
  revised first.
