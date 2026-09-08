## Configuration / Ignore / Expiry Contract

This document defines the public meaning of `.orb-lint.yml`: what the file may
contain, how an ignore is scoped, and when an ignore stops applying.

Origin: Phase 3-2 / Redmine #5377, under Phase 3 / #5380.
Refined by: Phase 3-2-1 / #5384 (ownership boundary, exact-path reservation,
ignored-finding reporting, dependency policy).
Related work: failure classification is Phase 3-1 / #5376 in
`docs/failure-model.md`; serialization is Phase 3-3 / #5378 in
`docs/adr/0014-json-schema-v1.md`; integration verification is Phase 3-4 /
#5379 in `docs/phase-3-4-verification.md`.
Design decision: `docs/adr/0004-configuration-and-ignore-contract.md`.
Repository location: `docs/configuration-contract.md`.

### Ownership

`orb_lint/_configuration.py` is the single authoritative implementation of this
contract. Parsing, schema validation, semantic validation, normalization, ignore
matching, and expiry all live there. Reimplementing any of these semantics in a
second place would let the two drift, so that duplication is a defect rather
than an optimization.

Two things are deliberately kept apart:

- **The public contract is this document**: the meaning of `.orb-lint.yml`.
- **The module is private.** Its path, classes, and functions are not a stable
  Python API. When `orb-lint-audit` needs the same semantics, Phase 6 will
  define the narrow public facade it actually requires, on top of this module.
  Audit must never reimplement the semantics; it must also not be the reason a
  private symbol becomes frozen before anyone has used it.

The decision and its history are in ADR-004.

### Parser dependency

`.orb-lint.yml` is parsed with PyYAML (`yaml.safe_load`). The dependency is
declared as `PyYAML>=6.0,<7`: the lower bound is the API the code uses, and the
upper bound is the major version verified by the test suite in CI. A
deterministic linter must not change behavior because dependency resolution
picked a different major on a different day. Raising the bound is a deliberate
change made with a passing test run, not something left to `pip`.

### File format

```yaml
ignore:
  - rule: ORB-003
    reason: repository specific permanent exception

  - rule: ORB-017
    path: .circleci/test-deploy.yml
    reason: development bootstrap only
    expires: 2026-12-31
```

`ignore` is the only recognized top-level key. A missing file, an empty file,
and an empty `ignore` are all valid and ignore nothing.

| key | required | meaning |
|---|---|---|
| `rule` | yes | the rule identity this entry applies to |
| `reason` | yes | why the exception exists; must be nonempty |
| `path` | no | restricts the entry to one file |
| `expires` | no | inclusive final day the entry applies |

Any unknown key, at either level, is rejected. A typo must fail loudly rather
than silently widen or narrow an exception.

### Rule identity

`rule` must look like a rule identity: `ORB-` followed by digits. Whether that
rule exists is deliberately **not** checked.

A repository may legitimately carry an ignore for a rule that its pinned checker
version does not implement yet. Validating existence would couple every
consumer's configuration to the checker version and make rolling out a rule a
breaking change for anyone who prepared for it early.

### Path scoping

Without `path`, the entry applies to every finding of that rule in the
repository. With `path`, it applies only to findings whose path is exactly that
file.

Paths are matched as **exact, repository-root-relative POSIX paths**. There is
no glob, prefix, or directory matching. `./` segments are normalized away and
surrounding whitespace is stripped.

These are rejected:

- absolute paths — the target is one repository, not a filesystem;
- any `..` segment — an ignore cannot reach outside the repository;
- a trailing `/` — directory scoping is not part of this contract;
- backslashes — one separator, so a path means the same thing everywhere;
- the characters `*`, `?`, and `[` — `path` is exact, and these are reserved so
  that a future pattern field cannot silently change what an existing `path`
  means. Any other punctuation (`@`, `-`, `.`) is an ordinary filename
  character.

Compatibility boundary: the meaning of `path` is fixed as exact match. If
pattern matching is ever needed it will be a separate, explicitly named field
(for example `path_glob`) with its own decision record, never a reinterpretation
of `path`.

### Expiry

`expires` takes an ISO date, quoted or unquoted. The entry applies **through the
end of that day** and stops applying the day after. There is no grace period.

The evaluation date is taken in UTC, so a repository does not expire an ignore
at a different moment depending on where CI happens to run.

When an entry expires, the original finding and its severity return unchanged.
Nothing is downgraded on the way out.

### Multiple matches

Several entries may match one finding. The finding is ignored when at least one
**active** entry matches, and the first such entry in file order is the one
attributed to it.

An expired entry never suppresses a finding, and never shadows a later active
entry that also matches.

### Boundary with measurement and enforcement

Ignoring is an enforcement concern. It is applied after evaluation, so:

- measurement still counts the finding, and the Phase 2 counts are unchanged;
- the lint outcome still reports violations;
- the finding stays on the execution result, marked with the entry that
  suppressed it.

An ignore suppresses enforcement; it does not erase the record that the finding
occurred, and it does not hide it from the reader either. With `--format json`
the finding is emitted with `ignored: true`, `ignore_reason`, and
`ignore_expires` (ADR-014).

### Human-readable reporting of ignored findings

Every finding is printed to stdout in evaluation order, whether ignored or not.
An ignored finding is followed by indented lines naming the entry that
suppressed it:

```text
.circleci/test-deploy.yml:8: ORB-001: publishing context placeholder ...
  ignored: development bootstrap only
  expires: 2026-12-31
orb-lint: OK (1 ignored finding)
```

- `ignored:` carries the entry's `reason` and is always present.
- `expires:` is present only when the entry has one.
- The `orb-lint: OK` line is printed when there is no active finding and no
  diagnostic. When ignored findings exist it carries a count, so that three
  states are distinguishable by output alone:

| state | stdout | exit |
|---|---|---|
| clean | `orb-lint: OK` (byte-identical to Phase 2) | `0` |
| ignored-only | findings marked `ignored:`, then `orb-lint: OK (N ignored finding[s])` | `0` |
| active | findings, unmarked or marked; no `OK` line | per severity |

The exit code is unaffected by ignored findings; only active findings and
diagnostics reach enforcement.

### Invalid configuration

Every rejection above raises a repository input failure carrying an `INPUT-002`
diagnostic and exits `1`, per `docs/failure-model.md`. An unusable configuration
is never reported as an `ORB-xxx` violation.

### Not in this Phase

- expiry inventory and 30-day notice (Phase 6, `orb-lint-audit`);
- any required link between an ignore and a Redmine issue;
- repository-name special cases in code — every exception is expressed in
  configuration;
- permission to use `expires` on error-severity rules, which stays a Phase 5
  operational constraint rather than a schema rule;
- glob or directory path matching.
