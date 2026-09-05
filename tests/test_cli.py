from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from orb_lint._execution import _run_repository
from orb_lint.cli import main
from orb_lint.rules.orb001 import MESSAGE


FIXTURES = Path(__file__).parent / "fixtures" / "orb001"


class CliTests(unittest.TestCase):
    def test_pass_returns_zero(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main([str(FIXTURES / "pass")])

        self.assertEqual(code, 0)
        self.assertIn("orb-lint: OK", output.getvalue())

    def test_violation_returns_one_and_prints_rule(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main([str(FIXTURES / "fail")])

        self.assertEqual(code, 1)
        self.assertIn("ORB-001", output.getvalue())
        self.assertIn("<publishing-context>", (FIXTURES / "fail" / ".circleci" / "test-deploy.yml").read_text())

    def test_cli_executes_measurement_and_preserves_exact_output(self) -> None:
        for fixture, count, code in (("pass", 0, 0), ("fail", 1, 1)):
            with self.subTest(fixture=fixture):
                executions = []

                def record(repository):
                    execution = _run_repository(repository)
                    executions.append(execution)
                    return execution

                output, errors = StringIO(), StringIO()
                with patch("orb_lint.cli._run_repository", side_effect=record):
                    with redirect_stdout(output), redirect_stderr(errors):
                        actual_code = main([str(FIXTURES / fixture)])

                expected = "orb-lint: OK\n" if code == 0 else (
                    f".circleci/test-deploy.yml:8: ORB-001: {MESSAGE}\n"
                )
                self.assertEqual(actual_code, code)
                self.assertEqual(output.getvalue(), expected)
                self.assertEqual(errors.getvalue(), "")
                self.assertEqual(len(executions), 1)
                measurement = executions[0].measurement
                self.assertEqual(measurement.outcome, "succeeded")
                self.assertEqual(measurement.value.rules[0].finding_count, count)

    def test_measurement_failure_preserves_cli_exit_and_diagnostics(self) -> None:
        for fixture, code in (("pass", 0), ("fail", 1)):
            with self.subTest(fixture=fixture):
                output, errors = StringIO(), StringIO()
                with patch("orb_lint._measurement._build_measurement", side_effect=RuntimeError("failed")) as build:
                    with redirect_stdout(output), redirect_stderr(errors):
                        actual_code = main([str(FIXTURES / fixture)])
                expected = "orb-lint: OK\n" if code == 0 else (
                    f".circleci/test-deploy.yml:8: ORB-001: {MESSAGE}\n"
                )
                build.assert_called_once()
                self.assertEqual(actual_code, code)
                self.assertEqual(output.getvalue(), expected)
                self.assertEqual(errors.getvalue(), "")

    def test_evaluation_error_is_not_converted_to_cli_success(self) -> None:
        output = StringIO()
        failure = OSError("lint input could not be read")
        with patch("orb_lint._execution.check_orb001", side_effect=failure):
            with redirect_stdout(output):
                with self.assertRaises(OSError) as caught:
                    main([str(FIXTURES / "pass")])
        self.assertIs(caught.exception, failure)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
