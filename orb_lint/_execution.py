"""Private execution boundary shared by the CLI and measurement verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from orb_lint._measurement import (
    _Evaluation,
    _MeasurementResult,
    _RuleEvaluation,
    _measure,
)
from orb_lint._configuration import (
    Configuration,
    IgnoreRule,
    _today,
    load_configuration,
)
from orb_lint.failure import Diagnostic, RepositoryInputError, Severity
from orb_lint.rules.orb001 import RULE_ID, Finding, check_orb001


@dataclass(frozen=True)
class _EvaluatedFinding:
    """A finding paired with the ignore entry that suppressed it, if any."""

    finding: Finding
    ignore: IgnoreRule | None = None

    @property
    def ignored(self) -> bool:
        return self.ignore is not None


@dataclass(frozen=True)
class _ExecutionResult:
    evaluation: _Evaluation
    measurement: _MeasurementResult
    # INPUT-xxx problems with the repository's own input or configuration.
    # Kept separate from findings so that policy violations stay distinguishable
    # from unusable input at the identity level.
    diagnostics: tuple[Diagnostic, ...] = ()
    # Every finding, ignored or not. Ignoring suppresses enforcement; it never
    # erases the record that the finding occurred.
    results: tuple[_EvaluatedFinding, ...] = ()
    configuration: Configuration = Configuration()

    @property
    def active_findings(self) -> tuple[Finding, ...]:
        return tuple(
            result.finding for result in self.results if not result.ignored
        )

    @property
    def ignored_findings(self) -> tuple[_EvaluatedFinding, ...]:
        return tuple(result for result in self.results if result.ignored)

    @property
    def severities(self) -> tuple[Severity, ...]:
        # Only findings that survive ignore evaluation reach enforcement.
        return tuple(finding.severity for finding in self.active_findings)


def _apply_ignores(
    findings: tuple[Finding, ...],
    configuration: Configuration,
    today: date,
) -> tuple[_EvaluatedFinding, ...]:
    return tuple(
        _EvaluatedFinding(
            finding,
            configuration.matching_ignore(
                rule_id=finding.rule_id, path=finding.path, today=today
            ),
        )
        for finding in findings
    )


def _run_repository(repository: Path) -> _ExecutionResult:
    target = repository.resolve()

    # Keep evaluation outside the measurement error boundary. Existing read or
    # decoding failures must still propagate, rather than becoming clean lint.
    # A RepositoryInputError is different: it is a classified statement about
    # the repository, so the run continues and reports it as a diagnostic with
    # the rule left explicitly not evaluated.
    try:
        configuration = load_configuration(target)
        findings = tuple(check_orb001(target))
    except RepositoryInputError as error:
        evaluation = _Evaluation(target, (_RuleEvaluation(RULE_ID, None),))
        return _ExecutionResult(
            evaluation, _measure(evaluation), (error.diagnostic,)
        )

    # Measurement observes evaluation, so it counts every finding. Ignoring is
    # an enforcement concern and must not change the Phase 2 counts.
    evaluation = _Evaluation(target, (_RuleEvaluation(RULE_ID, findings),))
    results = _apply_ignores(findings, configuration, _today())

    return _ExecutionResult(
        evaluation,
        _measure(evaluation),
        (),
        results,
        configuration,
    )
