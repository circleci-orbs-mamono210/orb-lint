"""Private execution boundary shared by the CLI and measurement verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orb_lint._measurement import (
    _Evaluation,
    _MeasurementResult,
    _RuleEvaluation,
    _measure,
)
from orb_lint.rules.orb001 import RULE_ID, check_orb001


@dataclass(frozen=True)
class _ExecutionResult:
    evaluation: _Evaluation
    measurement: _MeasurementResult


def _run_repository(repository: Path) -> _ExecutionResult:
    target = repository.resolve()
    # Keep evaluation outside the measurement error boundary. Existing read or
    # decoding failures must still propagate, rather than becoming clean lint.
    findings = tuple(check_orb001(target))
    evaluation = _Evaluation(target, (_RuleEvaluation(RULE_ID, findings),))
    return _ExecutionResult(evaluation, _measure(evaluation))
