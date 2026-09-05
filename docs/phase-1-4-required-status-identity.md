# Phase 1-4 required status identity spike

This document supports Redmine #5348. It intentionally does not predefine the
consumer repository, CircleCI/GitHub integration mode, reporting type, or
required-check identity. Those values must come from the actual consumer PR.

## Preconditions

- Phase 1-1 Walking Skeleton and ORB-001 are complete.
- Phase 1-2 development bootstrap is complete.
- Phase 1-3 release-tag immutability is active and verified.
- `orbss/orb-lint@0.0.1` and the matching immutable CLI tag `v0.0.1` are
  available before the production-consumer measurement starts.

## 1. Select one consumer repository

Choose exactly one existing Orb repository for the Phase 1 spike. Record the
repository name in the evidence notes. Do not roll out to all repositories in
this ticket.

## 2. Add the production Orb

Use `examples/phase-1-4/consumer-circleci.yml` as a merge example for the
consumer repository's existing `.circleci/config.yml`.

The production consumer must use:

```yaml
orbs:
  orb-lint: orbss/orb-lint@0.0.1
```

and must not pass `checker_ref`.

Create a consumer PR and confirm that `orb-lint/lint` reaches the checkout and
runs the released CLI against the consumer repository.

## 3. Collect GitHub reporting evidence

Record the success commit SHA, then run from the `orb-lint` repository:

```bash
python3 tools/status_identity.py collect \
  --repo OWNER/CONSUMER_REPO \
  --sha SUCCESS_SHA \
  --output phase-1-4-success.json
```

For a public repository the read may work without a token. If GitHub requires
a token, set `GITHUB_TOKEN` before running the command.

Inspect `identities` in the generated JSON. Determine which observed identity
belongs to the production orb-lint job from the actual PR/job links. Do not
infer the identity from the Orb job name alone.

## 4. Measure the failure path

Create a controlled consumer commit/PR state in which orb-lint fails, while
keeping the same CircleCI job/reporting path. Record that commit SHA and run:

```bash
python3 tools/status_identity.py collect \
  --repo OWNER/CONSUMER_REPO \
  --sha FAILURE_SHA \
  --output phase-1-4-failure.json
```

After the exact identity has been observed, compare the two measurements:

```bash
python3 tools/status_identity.py compare \
  --success phase-1-4-success.json \
  --failure phase-1-4-failure.json \
  --identity 'EXACT_IDENTITY_FROM_GITHUB' \
  --output phase-1-4-comparison.json
```

The comparison must show the same `type` and `identity` on both commits. The
provider should also remain stable. The result is expected to differ between
the controlled success and failure commits.

## 5. Record the integration mode separately

The API evidence above tells us what GitHub received; it does not prove the
CircleCI project integration configuration by itself. Verify the actual
CircleCI/GitHub integration used by the selected consumer repository and
record it as an observed fact.

Evidence fields:

- consumer repository:
- consumer PR:
- CircleCI project/integration mode:
- success SHA:
- failure SHA:
- reporting type (`status` or `check_run`):
- reporting unit (job/workflow/other observed unit):
- exact GitHub identity:
- provider/app:

## 6. Required-check spike

Using the exact measured identity, determine whether the selected consumer
repository can use that identity as a GitHub repository-ruleset required
status check.

Verify both directions:

1. the controlled failure leaves the required check unsatisfied and blocks the
   merge path under test;
2. the controlled success satisfies the same required-check identity.

Do not extrapolate from the `orb-lint` repository's development pipeline. The
Phase 1 contract is the value observed on the production consumer PR.

If job-level required check cannot be established, record the actual boundary
before Phase 2. Possible boundaries to inspect include the Orb job unit, the
consumer workflow shape, CircleCI-to-GitHub reporting unit, and the GitHub
ruleset enforcement model. Do not invent a workaround merely to close Phase 1.

## Completion evidence for #5348

- selected consumer repository and PR
- production `orbss/orb-lint@0.0.1` used without `checker_ref`
- released CLI actually inspected the checkout
- CircleCI/GitHub integration mode verified
- success JSON evidence
- failure JSON evidence
- exact identity comparison JSON
- required-check configuration/result evidence
- failure blocks merge and success satisfies the same identity, or an explicit
  architecture boundary if job-level enforcement is impossible
