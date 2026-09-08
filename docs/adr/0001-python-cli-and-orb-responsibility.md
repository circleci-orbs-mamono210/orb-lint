# ADR-001: Python CLI and Orb responsibility split

- Status: accepted
- Reconstructed: 2026-09-08
- Origin: Roadmap "技術選定" / "責務分界"; implemented in Phase 1-1 / Redmine
  #5345 and Phase 1-2 / #5346, under Phase 1 / #5344
- Recorded by: Phase 3-0-1 / Redmine #5385, under Phase 3 / #5380

## Note on reconstruction

This ADR was reconstructed after the decision had already been implemented. It
records the current authoritative decision and does not claim that this file
existed at the original decision date. The sources are the Roadmap, the closed
Phase 1 tickets, and the repository as it stands at the time of writing. Where
those sources are silent, this record is silent too.

## Context

orb-lint has two deliverables: a Python package (`orb_lint`, exposing the
`orb-lint` console script) and a CircleCI Orb (`orbss/orb-lint`, built with the
Orb Development Kit from `src/`). Both are needed: the Orb is how consumer
repositories run the check in CI, and the CLI is what actually decides whether
a repository conforms.

Two designs were possible. The policy logic could be embedded in the Orb, as a
single inlined script, or it could live in a separately installable package that
the Orb only invokes. The Roadmap chose the second and the Phase 1 tickets built
it that way.

## Decision

The Python CLI owns every decision about the repository. The Orb owns nothing
but the plumbing needed to run the CLI inside a CircleCI job.

### Owned by the Python CLI (`orb_lint`)

- policy rule evaluation (`orb_lint/rules/`);
- interpretation of `.orb-lint.yml` (`orb_lint/configuration.py`; see ADR-004);
- the result model, including measurement (`orb_lint/_measurement.py`,
  `docs/measurement-contract.md`);
- diagnostics and the `ORB-xxx` / `INPUT-xxx` identity namespaces (see
  ADR-003);
- exit semantics (`orb_lint/failure.py`, `docs/failure-model.md`);
- all deterministic policy logic, and its unit tests.

The CLI answers from the checked-out repository alone. It uses no external API.
A rule that would need GitHub or CircleCI state is not an orb-lint rule; the
Roadmap assigns such checks to `orb-lint-audit`.

### Owned by the Orb (`src/`)

- `checkout` of the consumer repository;
- installing the CLI from the orb-lint Git repository at a chosen ref
  (`src/scripts/install.sh`);
- invoking the CLI against the checkout (`src/scripts/run.sh`);
- CircleCI job integration: executor, job parameters, step ordering
  (`src/jobs/lint.yml`);
- accepting and passing through the `checker_ref` parameter.

The Orb does not reimplement, duplicate, or partially inline any policy logic.
It does not decide what the CLI's exit code means beyond returning it.

### Out of scope for this record

How the Orb version and the CLI ref are tied together (lockstep versioning,
the release-tag default of `checker_ref`, the development escape hatch) is a
separate decision. The Roadmap assigns it to ADR-010, and the immutability of
release tags to ADR-013. This record does not restate either.

## Rationale

The Roadmap gives the reasons directly:

- A CLI can be run and tested on its own, outside CircleCI. Embedding the
  logic in the Orb would tie every test to an Orb build.
- The CLI already needs several rules, a configuration parser, and (from
  Phase 3-3) a JSON formatter. Closing that into a single inlined script would
  make it unmaintainable and untestable.
- Distribution through `pip install git+...@<ref>` avoids a hard dependency on
  PyPI while still letting the Orb pin an exact tree.
- Keeping the Orb thin means a change in policy is a change in one place. If
  the Orb carried its own copy of any rule, the two copies could disagree, and
  a consumer could pass or fail depending on which one ran.

The "checkout only" boundary follows from the Roadmap's split between orb-lint
(blocks merges, must be fail-closed, runs per PR) and orb-lint-audit (informs,
fail-open, runs weekly, may call external APIs). A merge gate that depends on
an external API would fail for reasons unrelated to the PR.

## Consequences

- Every new rule is Python code with a unit test; the Orb does not change when
  a rule is added.
- The Orb's scripts stay short enough to read in full. Their only branching is
  the E2E test hooks (`ORB_LINT_EXPECTED_EXIT_CODE`,
  `ORB_LINT_EXPECT_INSTALL_FAILURE`), which exist to verify the Orb's plumbing,
  not to alter policy.
- A CircleCI-side concern (executor image, caching, reporting identity) is an
  Orb change; a repository-side concern is a CLI change. Reviewers can tell
  which from the diff path alone.
- `orb-lint-audit`, when it exists, depends on the `orb_lint` package for any
  shared semantics rather than on the Orb.
