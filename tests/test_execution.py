from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orb_lint._execution import _run_repository
from orb_lint.rules.orb001 import check_orb001


FIXTURES = Path(__file__).parent / "fixtures" / "orb001"


class ExecutionTests(unittest.TestCase):
    def _semantic_baseline(self, result, *, target_id: str) -> dict[str, object]:
        self.assertEqual(result.measurement.outcome, "succeeded")
        measurement = result.measurement.value
        self.assertIsNotNone(measurement)
        return {
            "target": target_id,
            "rules": tuple(
                (rule.rule_id, rule.evaluated, rule.finding_count)
                for rule in measurement.rules
            ),
            "lint_outcome": measurement.lint_outcome,
            "measurement_outcome": result.measurement.outcome,
        }

    def test_existing_zero_and_single_finding_inputs_are_measured(self) -> None:
        for fixture, count, outcome in (("pass", 0, "passed"), ("fail", 1, "violations")):
            with self.subTest(fixture=fixture):
                target = FIXTURES / fixture
                result = _run_repository(target)
                self.assertEqual(result.evaluation.target, target.resolve())
                self.assertEqual(result.evaluation.lint_outcome, outcome)
                self.assertEqual(result.measurement.outcome, "succeeded")
                self.assertEqual(result.measurement.value.target, target.resolve())
                self.assertEqual(result.measurement.value.lint_outcome, outcome)
                rules = result.measurement.value.rules
                self.assertEqual(len(rules), 1)
                self.assertEqual(rules[0].rule_id, "ORB-001")
                self.assertTrue(rules[0].evaluated)
                self.assertEqual(rules[0].finding_count, count)
                self.assertEqual(result.evaluation.findings, tuple(check_orb001(target)))

    def test_representative_measurement_baseline(self) -> None:
        expected = {
            "pass": {
                "target": "pass",
                "rules": (("ORB-001", True, 0),),
                "lint_outcome": "passed",
                "measurement_outcome": "succeeded",
            },
            "fail": {
                "target": "fail",
                "rules": (("ORB-001", True, 1),),
                "lint_outcome": "violations",
                "measurement_outcome": "succeeded",
            },
            "multiple": {
                "target": "multiple",
                "rules": (("ORB-001", True, 3),),
                "lint_outcome": "violations",
                "measurement_outcome": "succeeded",
            },
        }

        actual = {
            fixture: self._semantic_baseline(
                _run_repository(FIXTURES / fixture), target_id=fixture
            )
            for fixture in ("pass", "fail")
        }

        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".circleci").mkdir()
            (target / ".circleci" / "config.yml").write_text(
                "first: <publishing-context> <publishing-context>\n"
                "second: <publishing-context>\n",
                encoding="utf-8",
            )
            actual["multiple"] = self._semantic_baseline(
                _run_repository(target), target_id="multiple"
            )

        self.assertEqual(actual, expected)

    def test_representative_measurement_baseline_is_repeatable(self) -> None:
        for fixture in ("pass", "fail"):
            with self.subTest(fixture=fixture):
                target = FIXTURES / fixture
                first = self._semantic_baseline(
                    _run_repository(target), target_id=fixture
                )
                second = self._semantic_baseline(
                    _run_repository(target), target_id=fixture
                )
                self.assertEqual(first, second)

        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".circleci").mkdir()
            (target / ".circleci" / "config.yml").write_text(
                "first: <publishing-context> <publishing-context>\n"
                "second: <publishing-context>\n",
                encoding="utf-8",
            )
            first = self._semantic_baseline(
                _run_repository(target), target_id="multiple"
            )
            second = self._semantic_baseline(
                _run_repository(target), target_id="multiple"
            )

        self.assertEqual(first, second)

    def test_multiple_files_count_findings_not_placeholder_occurrences(self) -> None:
        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".circleci").mkdir()
            (target / ".circleci" / "config.yml").write_text(
                "first: <publishing-context> <publishing-context>\n"
                "second: <publishing-context>\n", encoding="utf-8",
            )
            (target / ".circleci" / "other.yaml").write_text(
                "third: <publishing-context>\n", encoding="utf-8",
            )
            result = _run_repository(target)

        self.assertEqual(result.measurement.outcome, "succeeded")
        self.assertEqual(result.measurement.value.rules[0].finding_count, 3)
        self.assertEqual(len(result.evaluation.findings), 3)
        self.assertEqual(result.evaluation.lint_outcome, "violations")

    def test_targets_keep_independent_counts_even_with_same_directory_name(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            first = parent / "a" / "repository"
            second = parent / "b" / "repository"
            (first / ".circleci").mkdir(parents=True)
            second.mkdir(parents=True)
            (first / ".circleci" / "config.yml").write_text(
                "context: <publishing-context>\n", encoding="utf-8",
            )
            result_a = _run_repository(first)
            result_b = _run_repository(second)

        self.assertNotEqual(result_a.measurement.value.target, result_b.measurement.value.target)
        self.assertEqual(result_a.measurement.value.target, first.resolve())
        self.assertEqual(result_b.measurement.value.target, second.resolve())
        self.assertEqual(result_a.measurement.value.rules[0].finding_count, 1)
        self.assertEqual(result_b.measurement.value.rules[0].finding_count, 0)

    def test_execution_calls_rule_once_and_retains_original_diagnostics(self) -> None:
        target = FIXTURES / "fail"
        with patch("orb_lint._execution.check_orb001", wraps=check_orb001) as checker:
            result = _run_repository(target)
        checker.assert_called_once_with(target.resolve())
        self.assertEqual(result.evaluation.findings, tuple(check_orb001(target)))

    def test_measurement_failure_keeps_the_original_evaluation(self) -> None:
        failure = RuntimeError("measurement failed")
        target = FIXTURES / "fail"
        with patch("orb_lint._measurement._build_measurement", side_effect=failure):
            result = _run_repository(target)

        self.assertEqual(result.measurement.outcome, "failed")
        self.assertIsNone(result.measurement.value)
        self.assertIs(result.measurement.error, failure)
        self.assertEqual(result.evaluation.target, target.resolve())
        self.assertEqual(result.evaluation.lint_outcome, "violations")
        self.assertEqual(result.evaluation.findings, tuple(check_orb001(target)))

    def test_evaluation_error_propagates_before_measurement(self) -> None:
        failure = OSError("cannot read lint input")
        with patch("orb_lint._execution.check_orb001", side_effect=failure):
            with patch("orb_lint._execution._measure") as measure:
                with self.assertRaises(OSError) as caught:
                    _run_repository(FIXTURES / "pass")
        self.assertIs(caught.exception, failure)
        measure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
