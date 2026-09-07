"""Phase 3-1 / Redmine #5376: public exit code and diagnostic semantics."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orb_lint.configuration import CONFIGURATION_FILENAME
from orb_lint.cli import main
from orb_lint.failure import (
    EXIT_OK,
    EXIT_OPERATIONAL,
    EXIT_REPOSITORY,
    INPUT_CONFIGURATION,
    INPUT_PREFIX,
    INPUT_UNREADABLE,
    RULE_PREFIX,
    Diagnostic,
    OperationalError,
    RepositoryInputError,
)
from orb_lint.rules.orb001 import MESSAGE, RULE_ID, Finding


FIXTURES = Path(__file__).parent / "fixtures" / "orb001"


def _run(argument: str) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([argument])
    return code, out.getvalue(), err.getvalue()


class ExitCodeContractTests(unittest.TestCase):
    def test_exit_codes_are_distinct_and_defined(self) -> None:
        self.assertEqual((EXIT_OK, EXIT_REPOSITORY, EXIT_OPERATIONAL), (0, 1, 2))

    def test_clean_repository_exits_zero(self) -> None:
        code, out, err = _run(str(FIXTURES / "pass"))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "orb-lint: OK\n")
        self.assertEqual(err, "")

    def test_error_policy_violation_exits_one(self) -> None:
        code, out, err = _run(str(FIXTURES / "fail"))
        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(f"{RULE_ID}: {MESSAGE}", out)
        self.assertEqual(err, "")

    def test_warning_only_findings_exit_zero_but_are_still_printed(self) -> None:
        warning = Finding(RULE_ID, "src/@orb.yml", 3, "advisory", "warning")
        with patch(
            "orb_lint._execution.check_orb001", return_value=[warning]
        ):
            code, out, err = _run(str(FIXTURES / "pass"))

        self.assertEqual(code, EXIT_OK)
        self.assertIn("src/@orb.yml:3", out)
        self.assertNotIn("orb-lint: OK", out)
        self.assertEqual(err, "")

    def test_one_error_among_warnings_still_exits_one(self) -> None:
        findings = [
            Finding(RULE_ID, "a.yml", 1, "advisory", "warning"),
            Finding(RULE_ID, "b.yml", 2, MESSAGE, "error"),
        ]
        with patch("orb_lint._execution.check_orb001", return_value=findings):
            code, _, _ = _run(str(FIXTURES / "pass"))

        self.assertEqual(code, EXIT_REPOSITORY)


class RepositoryInputTests(unittest.TestCase):
    def test_unreadable_lint_input_is_input_001_and_exits_one(self) -> None:
        failure = RepositoryInputError(
            Diagnostic(INPUT_UNREADABLE, ".circleci/config.yml", "unreadable")
        )
        with patch("orb_lint._execution.check_orb001", side_effect=failure):
            code, out, err = _run(str(FIXTURES / "pass"))

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(INPUT_UNREADABLE, err)
        self.assertNotIn(RULE_PREFIX, err)
        self.assertEqual(out, "")

    def test_undecodable_lint_input_is_reported_as_input_not_orb(self) -> None:
        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".circleci").mkdir()
            (target / ".circleci" / "config.yml").write_bytes(b"\xff\xfe\x00bad")
            code, out, err = _run(str(target))

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(INPUT_UNREADABLE, err)
        self.assertNotIn(RULE_ID, err)
        self.assertEqual(out, "")

    def test_unreadable_configuration_is_input_002_and_exits_one(self) -> None:
        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / CONFIGURATION_FILENAME).write_bytes(b"\xff\xfe\x00bad")
            code, out, err = _run(str(target))

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(INPUT_CONFIGURATION, err)
        self.assertIn(CONFIGURATION_FILENAME, err)
        self.assertNotIn(RULE_PREFIX, err)
        self.assertEqual(out, "")

    def test_missing_configuration_is_not_a_failure(self) -> None:
        code, out, err = _run(str(FIXTURES / "pass"))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(err, "")
        self.assertEqual(out, "orb-lint: OK\n")

    def test_input_failure_leaves_the_rule_explicitly_not_evaluated(self) -> None:
        from orb_lint._execution import _run_repository

        failure = RepositoryInputError(
            Diagnostic(INPUT_UNREADABLE, ".circleci/config.yml", "unreadable")
        )
        with patch("orb_lint._execution.check_orb001", side_effect=failure):
            result = _run_repository(FIXTURES / "pass")

        rule = result.measurement.value.rules[0]
        self.assertEqual(rule.rule_id, RULE_ID)
        self.assertFalse(rule.evaluated)
        self.assertIsNone(rule.finding_count)
        self.assertEqual(result.evaluation.lint_outcome, "incomplete")
        self.assertEqual(result.diagnostics, (failure.diagnostic,))
        self.assertEqual(result.evaluation.findings, ())


class OperationalFailureTests(unittest.TestCase):
    def test_declared_operational_failure_exits_two(self) -> None:
        with patch(
            "orb_lint.cli._run_repository",
            side_effect=OperationalError("checker could not run"),
        ):
            code, out, err = _run(str(FIXTURES / "pass"))

        self.assertEqual(code, EXIT_OPERATIONAL)
        self.assertIn("operational failure", err)
        self.assertEqual(out, "")

    def test_unclassified_defect_exits_two_not_one(self) -> None:
        with patch(
            "orb_lint.cli._run_repository", side_effect=RuntimeError("defect")
        ):
            code, out, err = _run(str(FIXTURES / "pass"))

        self.assertEqual(code, EXIT_OPERATIONAL)
        self.assertNotEqual(code, EXIT_REPOSITORY)
        self.assertEqual(out, "")

    def test_operational_failure_is_not_reported_as_a_finding(self) -> None:
        with patch(
            "orb_lint.cli._run_repository", side_effect=RuntimeError("defect")
        ):
            code, out, err = _run(str(FIXTURES / "pass"))

        self.assertEqual(code, EXIT_OPERATIONAL)
        self.assertNotIn(RULE_PREFIX, out)
        self.assertNotIn(RULE_PREFIX, err)
        self.assertNotIn(INPUT_PREFIX, err)

    def test_measurement_failure_is_not_an_operational_exit(self) -> None:
        # Phase 2 boundary: measurement failure never changes the repository
        # facing result.
        for fixture, expected in (("pass", EXIT_OK), ("fail", EXIT_REPOSITORY)):
            with self.subTest(fixture=fixture):
                with patch(
                    "orb_lint._measurement._build_measurement",
                    side_effect=RuntimeError("failed"),
                ):
                    code, _, err = _run(str(FIXTURES / fixture))
                self.assertEqual(code, expected)
                self.assertEqual(err, "")


class IdentitySeparationTests(unittest.TestCase):
    def test_diagnostic_identity_cannot_use_the_rule_namespace(self) -> None:
        with self.assertRaises(ValueError):
            Diagnostic("ORB-001", "src/@orb.yml", "not a diagnostic")

    def test_input_and_rule_namespaces_do_not_overlap(self) -> None:
        self.assertFalse(INPUT_UNREADABLE.startswith(RULE_PREFIX))
        self.assertFalse(INPUT_CONFIGURATION.startswith(RULE_PREFIX))
        self.assertFalse(RULE_ID.startswith(INPUT_PREFIX))

    def test_orb001_keeps_error_severity(self) -> None:
        code, _, _ = _run(str(FIXTURES / "fail"))
        self.assertEqual(code, EXIT_REPOSITORY)


if __name__ == "__main__":
    unittest.main()
