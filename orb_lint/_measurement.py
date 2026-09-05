"""Private projection of lint evaluations; see docs/measurement-contract.md."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from orb_lint.rules.orb001 import Finding


_LintOutcome = Literal["passed", "violations", "incomplete"]


@dataclass(frozen=True)
class _RuleEvaluation:
    rule_id: str
    # None means no completed evaluation; an empty tuple means evaluated zero.
    findings: tuple[Finding, ...] | None


@dataclass(frozen=True)
class _Evaluation:
    target: Path
    # Includes every rule expected for this execution, even evaluated-zero rules.
    rules: tuple[_RuleEvaluation, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(
            finding
            for rule in self.rules
            if rule.findings is not None
            for finding in rule.findings
        )

    @property
    def lint_outcome(self) -> _LintOutcome:
        # Determine lint outcome from evaluation, independently of measurement.
        if any(rule.findings is None for rule in self.rules):
            return "incomplete"
        if any(rule.findings for rule in self.rules):
            return "violations"
        return "passed"


@dataclass(frozen=True)
class _RuleMeasurement:
    rule_id: str
    finding_count: int | None

    @property
    def evaluated(self) -> bool:
        return self.finding_count is not None


@dataclass(frozen=True)
class _Measurement:
    target: Path
    rules: tuple[_RuleMeasurement, ...]
    lint_outcome: _LintOutcome


@dataclass(frozen=True)
class _MeasurementResult:
    value: _Measurement | None
    error: Exception | None

    @property
    def outcome(self) -> Literal["succeeded", "failed"]:
        return "succeeded" if self.value is not None else "failed"


def _build_measurement(evaluation: _Evaluation) -> _Measurement:
    rules: list[_RuleMeasurement] = []
    seen: set[str] = set()

    for rule in evaluation.rules:
        if not isinstance(rule.rule_id, str) or not rule.rule_id.strip():
            raise ValueError("Measurement requires a nonempty rule identity")
        if rule.rule_id in seen:
            raise ValueError("Measurement requires unique rule identities")
        seen.add(rule.rule_id)

        if rule.findings is None:
            rules.append(_RuleMeasurement(rule.rule_id, None))
            continue

        # Do not silently attribute another rule's diagnostics to this rule.
        if any(finding.rule_id != rule.rule_id for finding in rule.findings):
            raise ValueError("Finding identity does not match its evaluated rule")
        rules.append(_RuleMeasurement(rule.rule_id, len(rule.findings)))

    return _Measurement(evaluation.target, tuple(rules), evaluation.lint_outcome)


def _measure(evaluation: _Evaluation) -> _MeasurementResult:
    try:
        return _MeasurementResult(_build_measurement(evaluation), None)
    except Exception as error:
        # Only measurement construction is inside this boundary. Lint evaluation
        # errors and process-control exceptions must retain their own behavior.
        return _MeasurementResult(None, error)
