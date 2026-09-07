## Configuration / Ignore / Expiry Contract

This document defines the public meaning of `.orb-lint.yml`: what the file may
contain, how an ignore is scoped, and when an ignore stops applying.

Origin: Phase 3-2 / Redmine #5377, under Phase 3 / #5380.
Related work: failure classification is Phase 3-1 / #5376 in
`docs/failure-model.md`; serialization is Phase 3-3; integration verification is
Phase 3-4 / #5379.
Design decision: `docs/adr/0004-configuration-and-ignore-contract.md`.
Repository location: `docs/configuration-contract.md`.

### Ownership

`orb_lint/configuration.py` is the single authoritative implementation of this
contract. Parsing, schema validation, semantic validation, normalization, ignore
matching, and expiry all live there.

The module is public for one reason: a future `orb-lint-audit` must import it.
Reimplementing any of these semantics in a second place would let the two drift,
so that duplication is a defect rather than an optimization.

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
no glob or prefix matching in this Phase. `./` segments are normalized away and
surrounding whitespace is stripped.

These are rejected:

- absolute paths — the target is one repository, not a filesystem;
- any `..` segment — an ignore cannot reach outside the repository;
- a trailing `/` — directory scoping is not part of this contract;
- backslashes — one separator, so a path means the same thing everywhere.

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

Only the exit code and the human-readable output change. An ignore suppresses
enforcement; it does not erase the record that the finding occurred. Phase 3-3
surfaces ignored findings in the JSON output.

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
