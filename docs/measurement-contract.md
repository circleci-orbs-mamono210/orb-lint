## Measurement Contract / Result Model

This document defines the measurement semantics that implementations and
regression checks must preserve. It does not add a public serialization schema,
a CLI option, or an enforcement policy. Private types and any separately
reviewed public output must preserve these semantics.

Origin: Phase 2-1 / Redmine #5350, under Phase 2 / #5349.
Related work: Phase 2-2 implementation / #5351 and Phase 2-3 verification / #5352.
Repository location: `docs/measurement-contract.md`.

### Responsibility boundary

A lint run has three distinct responsibilities:

1. **Lint evaluation** evaluates an identified rule against an identified
   target and produces diagnostics (`Finding` values in the current code).
2. **Measurement** projects evaluation outcomes into countable rule results.
3. **Enforcement** decides the CLI result and displays diagnostics.

Measurement observes evaluation. It does not redefine what ORB-001 detects,
turn a measurement error into a lint violation, or change the current CLI
contract: no findings succeeds; one or more findings are printed and fail.

### Measurement execution

One measurement execution represents one attempt to evaluate a known rule set
against exactly one lint target. The execution owns:

- one target identity;
- the rule identities expected for that execution;
- exactly one result state for each expected rule;
- a lint outcome that distinguishes completed from incomplete evaluation; and
- a measurement outcome that is independent of the lint outcome.

Results from separate executions must not be merged implicitly. In particular,
results for different targets remain separate even when their rule identities
and finding counts are equal.

An implementation may add timestamps or invocation metadata, but those values
are not part of this Phase's semantic identity or comparison contract.

### Target boundary

The current CLI accepts one repository path. The repository selected by that
argument is the target boundary for one execution.

Phase 2-2 must carry a target identity with the measurement so that two target
measurements cannot be confused. This Phase does not define a portable
repository identifier. An absolute path is runtime context, not a stable
cross-machine identity. A public or persisted target identifier requires a
separate contract decision before it is exposed.

### Stable rule identity

Rule aggregation uses the rule's stable machine identity. For the currently
implemented rule, that identity is `ORB-001`, sourced from the rule result's
`rule_id` contract.

The human-readable `message`, file path, and line number are diagnostic data.
They must not be used as the rule aggregation key. Editing diagnostic wording
must not create a new rule identity or split one rule's count.

Within one execution, each expected rule identity has exactly one rule result.
Multiple findings for the same rule increase that result's finding count; they
do not create multiple rule results.

### Rule result states

A successfully constructed measurement must represent each expected rule by
exactly one of these mutually exclusive states:

| State | Meaning | Finding count |
| --- | --- | --- |
| Evaluated | The rule completed evaluation. | Required, integer `>= 0`. |
| Not evaluated | The rule did not run or did not complete evaluation. | Absent; it must not be represented as zero. |

`evaluated` with a finding count of `0` means the rule ran successfully and
found no violations. Omitting an evaluated rule is not an alternative encoding
of zero findings.

For an evaluated rule, the finding count is the number of findings whose stable
`rule_id` equals that rule's identity in that execution. Findings with another
rule identity must never contribute to the count.

`not evaluated` records absence of an evaluation result. Phase 2-1 does not
introduce a skip or activation policy. Phase 2-2 may use this state only at an
actual evaluation boundary; it must not invent a public way to skip ORB-001
solely to demonstrate the state.

### Execution lint outcome

When every expected rule is evaluated, the execution's lint outcome is derived
from the evaluated rule results:

- total finding count `0`: lint passed;
- total finding count greater than `0`: lint violations found.

If an expected rule is not evaluated, the execution's lint outcome is
incomplete. Finding counts from rules that did complete remain associated with
those rules. A complete lint outcome must not be inferred from the available
counts. In particular, an incomplete execution must not be reported as lint
passed merely because all available counts are zero.

This is a semantic result model. It does not add or rename CLI exit codes.

### Measurement outcome

Measurement success describes whether the measurement processing succeeded,
independently of whether lint evaluation completed or found violations.

- Succeeded: the measurement faithfully represents the target, expected rule
  identities, their evaluated or not-evaluated states, applicable finding
  counts, and the lint outcome. Construction, validation, and any output step
  required by the chosen measurement interface have succeeded.
- Failed: constructing, validating, or emitting the required measurement
  failed. A reliable successful measurement must not be inferred from missing
  or partial output.

A rule's not-evaluated state is valid measurement information. When that state
is recorded correctly, the lint outcome is incomplete while the measurement
outcome is succeeded. Not evaluated by itself is not a measurement failure.

Conversely, completed evaluation does not guarantee measurement success.
Measurement failure must preserve any independently known lint outcome; it
must not replace a known lint result with a different result. Measurement
success must never be used as proof that lint passed.

### Failure boundary

A lint violation is expected evaluation output. A measurement failure is an
operational failure while constructing, validating, or emitting the
measurement. They are different result categories.

The following cases must remain distinguishable:

| Evaluation | Measurement | Meaning |
| --- | --- | --- |
| Completed, zero findings | Succeeded | Evaluated and clean. |
| Completed, findings present | Succeeded | Lint violations found. |
| Completed, zero findings | Failed | Lint passed, but measurement processing failed. |
| Completed, findings present | Failed | Lint violations exist, and measurement processing also failed. |
| Not completed | Succeeded | The incomplete lint outcome and not-evaluated states were recorded correctly. |
| Not completed | Failed | Lint is incomplete, and measurement processing also failed. |

A measurement failure must not:

- create a synthetic `Finding`;
- use `ORB-001` as an error identity;
- be encoded as `findings = 0`;
- turn a lint violation into success; or
- be counted as a lint violation.

The concrete exception and process-exit behavior remains governed by the
existing CLI error boundary until a public error contract is explicitly
approved. Phase 2-2 must not silently add a public error model while
implementing this contract.

### Multiple-rule compatibility

Although only ORB-001 is implemented today, the measurement boundary is a
collection keyed by stable rule identity, not an ORB-001-specific scalar.
Adding another rule must allow both results to coexist within the same
execution without changing the meaning of the ORB-001 result.

The contract requires identity uniqueness and correct per-rule counts. It does
not make rule ordering part of the public contract.

### Contract examples

These examples are semantic and deliberately do not prescribe JSON, Python
class names, or field names.

#### Evaluated with no violation

```text
execution target: repository A
rule ORB-001: evaluated, findings 0
lint outcome: passed
measurement outcome: succeeded
```

#### Multiple findings

```text
execution target: repository A
rule ORB-001: evaluated, findings 2
lint outcome: violations found
measurement outcome: succeeded
```

#### Not evaluated, successfully measured

```text
execution target: repository A
rule ORB-001: not evaluated, no finding count
lint outcome: incomplete
measurement outcome: succeeded
```

The result correctly records that ORB-001 did not complete evaluation. It does
not assert that ORB-001 passed, and it does not imply a measurement failure.

#### Completed evaluation, measurement failed

```text
execution target: repository A
known evaluation result: ORB-001 evaluated, findings 0
lint outcome: passed
measurement outcome: failed
```

Here the zero count is known from completed lint evaluation. It is not inferred
from missing measurement output. The example describes independent outcomes;
it does not require a successfully emitted measurement artifact after an
output failure.

#### Separate targets

```text
execution 1: repository A, ORB-001 evaluated, findings 1
execution 2: repository B, ORB-001 evaluated, findings 0
```

The two counts belong to different executions and must not be combined without
a later, explicit aggregation contract.

### Phase 2-2 implementation obligations

Phase 2-2 can choose private classes, helpers, and collections, but must provide
an implementation boundary that can demonstrate all of the following:

- one execution is associated with one target;
- ORB-001 is represented by stable identity, independently of its message;
- zero, one, and multiple ORB-001 findings produce exact counts;
- evaluated zero is explicit and differs from not evaluated;
- separate rules and separate targets cannot contaminate each other's counts;
- a correctly recorded not-evaluated state can coexist with measurement
  success and an incomplete lint outcome;
- measurement success is not used to infer lint success;
- measurement failure is not represented as a finding or clean lint result
  and does not overwrite an independently known lint outcome;
- the current ORB-001 detection and CLI success/failure meanings are unchanged.

If Phase 2-2 needs a public CLI option, serialized schema, persisted target
identity, new exit code, or new error contract, that public-contract change
must be reviewed explicitly. It is not authorized by this document alone.

### Phase 2-3 verification obligations

Phase 2-3 must use this same semantic contract for deterministic baseline and
regression checks. At minimum it must compare target separation, rule identity,
evaluation state, exact finding count, lint outcome, and measurement outcome.

Regression checks must cover the independence of these outcomes:

- a correctly recorded not-evaluated state yields an incomplete lint outcome
  and a successful measurement, without a finding count for that rule;
- measurement success does not convert incomplete lint into passed lint;
- measurement failure remains distinguishable when lint has passed, found
  violations, or remained incomplete, without altering the known lint outcome.

Where no production path produces a not-evaluated state, verify that state at
an internal contract boundary without introducing a new public skip policy.
These are verification obligations for Phase 2-2 / Phase 2-3, not claims that
measurement tests have already been implemented or executed.

Values outside this contract, such as absolute paths, timestamps, object
identity, or unspecified ordering, must not cause a semantic regression unless
a later public contract explicitly includes them.

### Out of scope

- a public serialization schema or structured-output format;
- a new public CLI option or exit-code contract;
- a portable repository identity;
- rule activation, skip, or severity policy;
- changing ORB-001 detection or diagnostic wording;
- baseline storage and regression thresholds;
- cross-repository aggregation or historical persistence;
- CI enforcement changes, dashboards, auto-fix, grace periods, release policy,
  `DRIFT`, or `OUTDATED` classification.

### Completion evidence

- the execution, target, rule identity, rule result, lint outcome, and
  measurement outcome meanings are defined;
- evaluated zero and not evaluated are mutually distinguishable;
- exact per-rule finding counts and multiple-target separation are defined;
- lint evaluation, measurement, and enforcement responsibilities are separate;
- violations and measurement failures cannot be confused;
- incomplete lint and successful measurement can coexist when the incomplete
  state is recorded correctly;
- measurement failure does not overwrite an independently known lint outcome;
- ORB-001 and current CLI behavior are compatibility constraints;
- Phase 2-2 and Phase 2-3 obligations are stated without fixing unconfirmed
  files, private implementation types, or public serialization.
