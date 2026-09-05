from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from unittest.mock import patch

from orb_lint._measurement import _Evaluation, _RuleEvaluation, _measure
from orb_lint.rules.orb001 import Finding


class MeasurementTests(unittest.TestCase):
    def evaluation(self, *rules: _RuleEvaluation) -> _Evaluation:
        return _Evaluation(Path("repository-a"), tuple(rules))

    def finding(self, rule_id: str, message: str = "diagnostic") -> Finding:
        return Finding(rule_id, "sample.yml", 1, message)

    def test_zero_is_explicit_and_not_evaluated_has_no_count(self) -> None:
        evaluation = self.evaluation(
            _RuleEvaluation("ORB-001", ()),
            _RuleEvaluation("TEST-PENDING", None),
        )
        result = _measure(evaluation)

        self.assertEqual(result.outcome, "succeeded")
        self.assertIsNone(result.error)
        self.assertEqual(result.value.lint_outcome, "incomplete")
        rules = {rule.rule_id: rule for rule in result.value.rules}
        self.assertTrue(rules["ORB-001"].evaluated)
        self.assertEqual(rules["ORB-001"].finding_count, 0)
        self.assertFalse(rules["TEST-PENDING"].evaluated)
        self.assertIsNone(rules["TEST-PENDING"].finding_count)

    def test_multiple_rules_keep_counts_and_identity_separate(self) -> None:
        evaluation = self.evaluation(
            _RuleEvaluation("TEST-B", (self.finding("TEST-B"),)),
            _RuleEvaluation("ORB-001", (
                self.finding("ORB-001"), self.finding("ORB-001"),
            )),
            _RuleEvaluation("TEST-ZERO", ()),
        )
        result = _measure(evaluation)

        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(result.value.lint_outcome, "violations")
        self.assertEqual(
            {rule.rule_id: rule.finding_count for rule in result.value.rules},
            {"TEST-B": 1, "ORB-001": 2, "TEST-ZERO": 0},
        )

    def test_message_path_and_line_do_not_define_rule_identity(self) -> None:
        evaluation = self.evaluation(_RuleEvaluation("ORB-001", (
            Finding("ORB-001", "first.yml", 1, "old diagnostic"),
            Finding("ORB-001", "second.yml", 90, "new diagnostic"),
        )))
        result = _measure(evaluation)

        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(len(result.value.rules), 1)
        self.assertEqual(result.value.rules[0].rule_id, "ORB-001")
        self.assertEqual(result.value.rules[0].finding_count, 2)

    def test_incomplete_lint_preserves_completed_rule_findings(self) -> None:
        finding = self.finding("ORB-001")
        evaluation = self.evaluation(
            _RuleEvaluation("ORB-001", (finding,)),
            _RuleEvaluation("TEST-PENDING", None),
        )
        result = _measure(evaluation)

        self.assertEqual(evaluation.findings, (finding,))
        self.assertEqual(evaluation.lint_outcome, "incomplete")
        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(result.value.lint_outcome, "incomplete")
        self.assertEqual(result.value.rules[0].finding_count, 1)
        self.assertIsNone(result.value.rules[1].finding_count)

    def test_lint_and_measurement_outcomes_are_independent(self) -> None:
        cases = (
            ((), "passed"),
            ((self.finding("ORB-001"),), "violations"),
            (None, "incomplete"),
        )
        for findings, expected_lint in cases:
            for fail_measurement in (False, True):
                with self.subTest(lint=expected_lint, failed=fail_measurement):
                    evaluation = self.evaluation(_RuleEvaluation("ORB-001", findings))
                    original_findings = evaluation.findings
                    failure = RuntimeError("measurement construction failed")
                    if fail_measurement:
                        with patch("orb_lint._measurement._build_measurement", side_effect=failure):
                            result = _measure(evaluation)
                        self.assertEqual(result.outcome, "failed")
                        self.assertIsNone(result.value)
                        self.assertIs(result.error, failure)
                    else:
                        result = _measure(evaluation)
                        self.assertEqual(result.outcome, "succeeded")
                        self.assertIsNone(result.error)
                        self.assertEqual(result.value.lint_outcome, expected_lint)
                    self.assertEqual(evaluation.lint_outcome, expected_lint)
                    self.assertEqual(evaluation.findings, original_findings)

    def test_duplicate_rule_identity_fails_measurement_without_merging(self) -> None:
        evaluation = self.evaluation(
            _RuleEvaluation("ORB-001", (self.finding("ORB-001"),)),
            _RuleEvaluation("ORB-001", ()),
        )
        result = _measure(evaluation)

        self.assertEqual(result.outcome, "failed")
        self.assertIsNone(result.value)
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(evaluation.lint_outcome, "violations")
        self.assertEqual(len(evaluation.findings), 1)

    def test_mismatched_finding_identity_fails_without_silent_loss(self) -> None:
        finding = self.finding("TEST-OTHER")
        evaluation = self.evaluation(_RuleEvaluation("ORB-001", (finding,)))
        result = _measure(evaluation)

        self.assertEqual(result.outcome, "failed")
        self.assertIsNone(result.value)
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(evaluation.findings, (finding,))

    def test_missing_rule_identity_fails_measurement(self) -> None:
        for identity in ("", " "):
            with self.subTest(identity=identity):
                result = _measure(self.evaluation(_RuleEvaluation(identity, ())))
                self.assertEqual(result.outcome, "failed")
                self.assertIsNone(result.value)
                self.assertIsInstance(result.error, ValueError)

    def test_successful_result_is_immutable(self) -> None:
        result = _measure(self.evaluation(_RuleEvaluation("ORB-001", ())))
        self.assertIsInstance(result.value.rules, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.value.rules[0].finding_count = 99

    def test_process_control_exceptions_are_not_measurement_failures(self) -> None:
        evaluation = self.evaluation(_RuleEvaluation("ORB-001", ()))
        for exception in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(exception=type(exception).__name__):
                with patch("orb_lint._measurement._build_measurement", side_effect=exception):
                    with self.assertRaises(type(exception)):
                        _measure(evaluation)


if __name__ == "__main__":
    unittest.main()
