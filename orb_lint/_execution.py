"""Private execution boundary shared by the CLI and measurement verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orb_lint._configuration import _load_configuration
from orb_lint._measurement import (
    _Evaluation,
    _MeasurementResult,
    _RuleEvaluation,
    _measure,
)
from orb_lint.failure import Diagnostic, RepositoryInputError, Severity
from orb_lint.rules.orb001 import RULE_ID, check_orb001


@dataclass(frozen=True)
class _ExecutionResult:
    evaluation: _Evaluation
    measurement: _MeasurementResult
    # INPUT-xxx problems with the repository's own input or configuration.
    # Kept separate from findings so that policy violations stay distinguishable
    # from unusable input at the identity level.
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def severities(self) -> tuple[Severity, ...]:
        return tuple(finding.severity for finding in self.evaluation.findings)


def _run_repository(repository: Path) -> _ExecutionResult:
    target = repository.resolve()

    # Keep evaluation outside the measurement error boundary. Existing read or
    # decoding failures must still propagate, rather than becoming clean lint.
    # A RepositoryInputError is different: it is a classified statement about
    # the repository, so the run continues and reports it as a diagnostic with
    # the rule left explicitly not evaluated.
    try:
        _load_configuration(target)
        findings = tuple(check_orb001(target))
    except RepositoryInputError as error:
        evaluation = _Evaluation(target, (_RuleEvaluation(RULE_ID, None),))
        return _ExecutionResult(
            evaluation, _measure(evaluation), (error.diagnostic,)
        )

    evaluation = _Evaluation(target, (_RuleEvaluation(RULE_ID, findings),))
    return _ExecutionResult(evaluation, _measure(evaluation))
