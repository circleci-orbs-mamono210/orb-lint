## Phase 3-4 Verification / Release Gate

This document records what Phase 3-4 verified, and what remains open before
Phase 3 can be released as `orb-lint v0.2.0`.

Origin: Phase 3-4 / Redmine #5379, under Phase 3 / #5380.
Repository location: `docs/phase-3-4-verification.md`.

### What this Phase verifies

Phases 3-1 (#5376), 3-2 (#5377), 3-2-1 (#5384), and 3-3 (#5378) each verified
one contract on its own. Phase 3-4 verifies them in combination, through the
real CLI, along the whole path:

```text
repository input
    -> configuration
    -> rule evaluation
    -> ignore / expiry evaluation
    -> findings / diagnostics
    -> text or JSON output
    -> exit code
```

The suite is `tests/test_integration.py`. It runs under the existing
verification route, so no new CI job is introduced:

```text
python -m unittest discover -s tests -v
```

### Cross-format consistency

Every scenario is executed twice, once per output format, and the two runs are
compared before any scenario-specific assertion:

- the exit codes must be equal;
- the findings must be equal, including which of them are ignored.

The human-readable output is parsed back for that comparison. A divergence
between what a person reads in the CI log and what a machine parses from
stdout is therefore a test failure here, rather than something Phase 4
discovers across ten repositories.

### Scenario matrix

| scenario | exit | verified |
|---|---|---|
| clean repository | `0` | `orb-lint: OK`, empty `findings` and `diagnostics`, empty stderr |
| warning-severity finding only | `0` | finding reported in both formats, `severity: warning` |
| active error finding | `1` | no `OK` line, `ignored: false`, null ignore metadata |
| rule-level ignore | `0` | `OK (1 ignored finding)`, `ignored: true` with reason, measurement count unchanged |
| ignore applied vs. not | `1` -> `0` | identical finding apart from ignore state |
| path-scoped ignore | `1` | development file ignored, production file still enforced |
| ignore on its expiry date | `0` | inclusive of the named day |
| ignore after expiry | `1` | finding and severity restored, no grace period |
| invalid `.orb-lint.yml` | `1` | `INPUT-002` on stderr and in `diagnostics`, no rule finding invented |
| undecodable lint input | `1` | `INPUT-001`, rule left **not evaluated** rather than zero findings |
| controlled operational failure | `2` | empty stdout in both formats, no `ORB-` or `INPUT-` identity in stderr |
| repeated execution | — | byte-identical stdout in both formats |
| ORB-001 fixtures | `0` / `1` | Phase 1 detection behavior unchanged |
| measurement failure | `1` | verdict unaffected in both formats |
| two targets | — | counts not merged, targets distinct |

Notes on two scenarios:

- **Warning-severity finding.** `ORB-001` keeps `error` severity; promoting or
  demoting rules is Phase 5 work and no rule was added or changed here. The
  warning-severity finding is injected at the rule boundary, so everything
  after evaluation — ignore matching, both formats, the exit code — is
  exercised for real.
- **Operational failure.** Raised from the rule boundary, which is the same
  path an unclassified defect would take.

### Fleet execution — open, blocking release

The Roadmap requires Phase 3 to be run against every target Orb repository,
confirming that no run produces exit `2` and no run produces an unexpected
`INPUT-xxx`.

**This is not yet done, and it is a release blocker for #5379 and #5380.**

The reason is that no authoritative inventory of target repositories has been
confirmed. Repository names are deliberately not guessed here: a list assembled
from memory could omit a repository, and recording an unverified list as
"verified" would be worse than recording nothing.

Automatic discovery is not the answer for this Phase either. Enumerating the
organization and testing for `src/@orb.yml` requires the GitHub API, which the
Roadmap assigns to `orb-lint-audit` in Phase 6. Building it here would put an
external API dependency inside Phase 3.

The intended resolution is a **snapshot**: once the target repositories are
confirmed, the list is recorded in the section below as the Phase 3 snapshot,
each repository is checked out and linted with the release candidate, and the
results are recorded. The snapshot is a record of what was verified at this
point in time, not a discovery mechanism, and Phase 6 replaces it with real
discovery.

#### Target repository snapshot

_Not yet confirmed. Fill in when the inventory is available._

| repository | commit | exit | unexpected `INPUT-xxx` |
|---|---|---|---|
| _(pending)_ | | | |

Verification procedure for each repository:

```text
git clone <repository>
orb-lint <checkout> --format json
```

Recorded per repository: the commit inspected, the exit code, and any
`diagnostics` entry. Expected outcomes:

- exit `2` never occurs;
- no unexpected `INPUT-xxx` diagnostic occurs. These repositories are not
  expected to carry `.orb-lint.yml` at all, so a configuration diagnostic
  would itself be a finding about Phase 3;
- exit `0` or `1` are both acceptable results at this stage. Phase 3 is not
  enforcement: a repository that violates `ORB-001` today is information for
  Phase 4 and Phase 5, not a defect in the Policy Engine.

### Phase 4 readiness

With the integration suite passing, Phase 4 can begin report-only deployment
without redesigning any Policy Engine contract: exit codes, diagnostic
identities, configuration and ignore semantics, and the JSON schema are all
fixed and regression-tested together.

The fleet execution above remains the one outstanding item. Until it is done,
Phase 3 has been verified on a single repository and on synthetic scenarios,
but not against the repositories it will be deployed to.
