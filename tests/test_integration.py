"""Phase 3-4 / Redmine #5379: Policy Engine integration regression.

Phase 3-1 (#5376), 3-2 (#5377), 3-2-1 (#5384), and 3-3 (#5378) each verified
their own contract in isolation. This suite exercises them together through
the real CLI, end to end:

    repository input -> configuration -> rule evaluation -> ignore/expiry
    -> findings/diagnostics -> text or JSON output -> exit code

Every scenario is run in both output formats and the two are compared, so
that a divergence between what a person reads and what a machine parses is a
test failure rather than something discovered in Phase 4.
"""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orb_lint._configuration import CONFIGURATION_FILENAME
from orb_lint._execution import _run_repository
from orb_lint.cli import main
from orb_lint.failure import (
    EXIT_OK,
    EXIT_OPERATIONAL,
    EXIT_REPOSITORY,
    INPUT_CONFIGURATION,
    INPUT_UNREADABLE,
)
from orb_lint.rules.orb001 import MESSAGE, RULE_ID, Finding


PLACEHOLDER = "context: <publishing-context>\n"
DEV = ".circleci/test-deploy.yml"
PROD = ".circleci/config.yml"

FIXTURES = Path(__file__).parent / "fixtures" / "orb001"


class Run:
    """One CLI invocation in one format."""

    def __init__(self, code: int, out: str, err: str) -> None:
        self.code = code
        self.out = out
        self.err = err


def _text_findings(out: str) -> list[tuple[str, int, str, bool]]:
    """Parse `(path, line, rule, ignored)` out of human-readable output.

    Parsing the text back is deliberate: it is the only way to assert that
    both formats report the same findings rather than merely the same exit
    code.
    """

    findings: list[tuple[str, int, str, bool]] = []
    for line in out.splitlines():
        if line.startswith("  ignored:"):
            path, number, rule, _ = findings[-1]
            findings[-1] = (path, number, rule, True)
            continue
        if line.startswith("  expires:") or line.startswith("orb-lint:"):
            continue
        location, rule, _ = line.split(": ", 2)
        path, number = location.rsplit(":", 1)
        findings.append((path, int(number), rule, False))
    return findings


def _json_findings(out: str) -> list[tuple[str, int, str, bool]]:
    document = json.loads(out)
    return [
        (f["path"], f["line"], f["rule"], f["ignored"])
        for f in document["findings"]
    ]


class IntegrationTestCase(unittest.TestCase):
    def repository(self, directory: str, *, files=(), configuration=None) -> Path:
        target = Path(directory)
        for relative in files:
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(PLACEHOLDER, encoding="utf-8")
        if configuration is not None:
            (target / CONFIGURATION_FILENAME).write_text(
                configuration, encoding="utf-8"
            )
        return target

    def _invoke(self, target: Path, *extra: str) -> Run:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(target), *extra])
        return Run(code, out.getvalue(), err.getvalue())

    def both(self, target: Path) -> tuple[Run, Run]:
        """Run the same repository in both formats and cross-check them.

        The two formats must agree on the exit code and on the findings,
        including which of them are ignored. Only the presentation differs.
        """

        text = self._invoke(target)
        js = self._invoke(target, "--format", "json")

        self.assertEqual(
            text.code, js.code, "exit code differs between text and JSON"
        )
        if js.code != EXIT_OPERATIONAL:
            self.assertEqual(
                sorted(_text_findings(text.out)),
                sorted(_json_findings(js.out)),
                "findings differ between text and JSON",
            )
        return text, js

    def document(self, run: Run) -> dict:
        return json.loads(run.out)


class CleanRepositoryTests(IntegrationTestCase):
    def test_clean_repository(self) -> None:
        with TemporaryDirectory() as directory:
            text, js = self.both(self.repository(directory))

        self.assertEqual(text.code, EXIT_OK)
        self.assertEqual(text.out, "orb-lint: OK\n")
        self.assertEqual(text.err, "")
        self.assertEqual(self.document(js)["findings"], [])
        self.assertEqual(self.document(js)["diagnostics"], [])
        self.assertEqual(js.err, "")


class SeverityTests(IntegrationTestCase):
    def test_warning_only_exits_zero_and_is_reported(self) -> None:
        # ORB-001 keeps error severity; promoting or demoting rules is Phase 5
        # work. A warning-severity finding is injected at the rule boundary so
        # that the rest of the path -- ignore evaluation, both formats, exit
        # code -- is exercised for real.
        warning = Finding(RULE_ID, PROD, 3, MESSAGE, "warning")
        with TemporaryDirectory() as directory:
            target = self.repository(directory)
            with patch(
                "orb_lint._execution.check_orb001", return_value=[warning]
            ):
                text, js = self.both(target)

        self.assertEqual(text.code, EXIT_OK)
        self.assertIn(f"{PROD}:3: {RULE_ID}", text.out)
        [finding] = self.document(js)["findings"]
        self.assertEqual(finding["severity"], "warning")
        self.assertFalse(finding["ignored"])

    def test_active_error_finding_exits_one(self) -> None:
        with TemporaryDirectory() as directory:
            text, js = self.both(self.repository(directory, files=(PROD,)))

        self.assertEqual(text.code, EXIT_REPOSITORY)
        self.assertNotIn("orb-lint: OK", text.out)
        [finding] = self.document(js)["findings"]
        self.assertEqual(finding["severity"], "error")
        self.assertFalse(finding["ignored"])
        self.assertIsNone(finding["ignore_reason"])


class IgnoreIntegrationTests(IntegrationTestCase):
    def test_rule_level_ignore_suppresses_enforcement_only(self) -> None:
        with TemporaryDirectory() as directory:
            target = self.repository(
                directory,
                files=(PROD,),
                configuration=(
                    f"ignore:\n  - rule: {RULE_ID}\n    reason: permanent\n"
                ),
            )
            text, js = self.both(target)
            result = _run_repository(target)

        self.assertEqual(text.code, EXIT_OK)
        self.assertTrue(text.out.endswith("orb-lint: OK (1 ignored finding)\n"))
        [finding] = self.document(js)["findings"]
        self.assertTrue(finding["ignored"])
        self.assertEqual(finding["ignore_reason"], "permanent")
        self.assertIsNone(finding["ignore_expires"])
        # Phase 2 boundary: measurement observes evaluation, not enforcement.
        self.assertEqual(result.measurement.value.rules[0].finding_count, 1)

    def test_ignoring_changes_exit_code_but_not_the_finding(self) -> None:
        # The same repository, with and without the ignore. The finding itself
        # is identical; only enforcement differs.
        configuration = (
            f"ignore:\n  - rule: {RULE_ID}\n    reason: permanent\n"
        )
        with TemporaryDirectory() as directory:
            _, before = self.both(self.repository(directory, files=(PROD,)))
        with TemporaryDirectory() as directory:
            _, after = self.both(
                self.repository(
                    directory, files=(PROD,), configuration=configuration
                )
            )

        self.assertEqual(before.code, EXIT_REPOSITORY)
        self.assertEqual(after.code, EXIT_OK)

        def without_ignore_state(document: dict) -> list[dict]:
            return [
                {k: v for k, v in f.items() if not k.startswith("ignore")}
                for f in document["findings"]
            ]

        self.assertEqual(
            without_ignore_state(self.document(before)),
            without_ignore_state(self.document(after)),
        )

    def test_path_scoped_ignore_stays_limited_in_the_integration_path(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            target = self.repository(
                directory,
                files=(DEV, PROD),
                configuration=(
                    f"ignore:\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    path: {DEV}\n"
                    f"    reason: development bootstrap only\n"
                ),
            )
            text, js = self.both(target)

        # One file exempt, the other still enforced: exit 1 overall.
        self.assertEqual(text.code, EXIT_REPOSITORY)
        states = {
            f["path"]: (f["ignored"], f["ignore_reason"])
            for f in self.document(js)["findings"]
        }
        self.assertEqual(states[DEV], (True, "development bootstrap only"))
        self.assertEqual(states[PROD], (False, None))

    def test_expired_ignore_restores_the_finding(self) -> None:
        expires = date(2026, 12, 31)
        configuration = (
            f"ignore:\n"
            f"  - rule: {RULE_ID}\n"
            f"    reason: temporary\n"
            f"    expires: {expires.isoformat()}\n"
        )
        with TemporaryDirectory() as directory:
            target = self.repository(
                directory, files=(PROD,), configuration=configuration
            )
            with patch("orb_lint._execution._today", return_value=expires):
                _, on_the_day = self.both(target)
            with patch(
                "orb_lint._execution._today", return_value=date(2027, 1, 1)
            ):
                text_after, after = self.both(target)

        # Inclusive of the named day, then gone with no grace period.
        self.assertEqual(on_the_day.code, EXIT_OK)
        self.assertTrue(self.document(on_the_day)["findings"][0]["ignored"])

        self.assertEqual(text_after.code, EXIT_REPOSITORY)
        [restored] = self.document(after)["findings"]
        self.assertFalse(restored["ignored"])
        self.assertIsNone(restored["ignore_reason"])
        self.assertIsNone(restored["ignore_expires"])
        self.assertEqual(restored["severity"], "error")


class RepositoryFailureTests(IntegrationTestCase):
    def test_invalid_configuration_is_a_repository_failure(self) -> None:
        with TemporaryDirectory() as directory:
            target = self.repository(
                directory, files=(PROD,), configuration="ignore: [\n"
            )
            text, js = self.both(target)

        self.assertEqual(text.code, EXIT_REPOSITORY)
        # Not a clean lint, and not converted into a rule finding.
        self.assertNotIn("orb-lint: OK", text.out)
        self.assertIn(INPUT_CONFIGURATION, text.err)
        document = self.document(js)
        self.assertEqual(document["findings"], [])
        [diagnostic] = document["diagnostics"]
        self.assertEqual(diagnostic["diagnostic"], INPUT_CONFIGURATION)
        self.assertEqual(diagnostic["path"], CONFIGURATION_FILENAME)

    def test_undecodable_lint_input_is_a_repository_failure(self) -> None:
        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".circleci").mkdir()
            (target / PROD).write_bytes(b"\xff\xfe\x00bad")
            text, js = self.both(target)

        self.assertEqual(text.code, EXIT_REPOSITORY)
        self.assertIn(INPUT_UNREADABLE, text.err)
        document = self.document(js)
        self.assertEqual(document["findings"], [])
        self.assertEqual(
            document["diagnostics"][0]["diagnostic"], INPUT_UNREADABLE
        )

    def test_a_rule_is_not_evaluated_when_input_fails(self) -> None:
        # Phase 2 distinction preserved end to end: an input failure leaves the
        # rule not evaluated, never evaluated-with-zero-findings.
        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / ".circleci").mkdir()
            (target / PROD).write_bytes(b"\xff\xfe\x00bad")
            result = _run_repository(target)

        [rule] = result.measurement.value.rules
        self.assertEqual(rule.rule_id, RULE_ID)
        self.assertFalse(rule.evaluated)
        self.assertIsNone(rule.finding_count)


class OperationalFailureTests(IntegrationTestCase):
    def test_controlled_operational_failure_is_exit_two_in_both_formats(
        self,
    ) -> None:
        failure = RuntimeError("checker defect")
        with TemporaryDirectory() as directory:
            target = self.repository(directory, files=(PROD,))
            with patch(
                "orb_lint._execution.check_orb001", side_effect=failure
            ):
                text, js = self.both(target)

        for run in (text, js):
            self.assertEqual(run.code, EXIT_OPERATIONAL)
            self.assertEqual(run.out, "")
            self.assertIn("operational failure", run.err)
            # Never disguised as a statement about the repository.
            self.assertNotIn("ORB-", run.err)
            self.assertNotIn("INPUT-", run.err)


class DeterminismTests(IntegrationTestCase):
    def test_repeated_execution_is_byte_identical(self) -> None:
        with TemporaryDirectory() as directory:
            target = self.repository(
                directory,
                files=(DEV, PROD),
                configuration=(
                    f"ignore:\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    path: {DEV}\n"
                    f"    reason: development bootstrap only\n"
                    f"    expires: 2026-12-31\n"
                ),
            )
            first = self._invoke(target, "--format", "json")
            second = self._invoke(target, "--format", "json")
            third = self._invoke(target)
            fourth = self._invoke(target)

        self.assertEqual((first.code, first.out), (second.code, second.out))
        self.assertEqual((third.code, third.out), (fourth.code, fourth.out))


class Phase2RegressionTests(IntegrationTestCase):
    def test_orb001_detection_is_unchanged(self) -> None:
        pass_run = self._invoke(FIXTURES / "pass")
        fail_run = self._invoke(FIXTURES / "fail")

        self.assertEqual(pass_run.code, EXIT_OK)
        self.assertEqual(pass_run.out, "orb-lint: OK\n")
        self.assertEqual(fail_run.code, EXIT_REPOSITORY)
        self.assertIn(RULE_ID, fail_run.out)

    def test_measurement_failure_does_not_change_the_verdict(self) -> None:
        # Measurement is observation. A measurement defect must not turn a
        # violation into a pass, in either format.
        with TemporaryDirectory() as directory:
            target = self.repository(directory, files=(PROD,))
            with patch(
                "orb_lint._measurement._build_measurement",
                side_effect=RuntimeError("measurement failed"),
            ):
                text, js = self.both(target)

        self.assertEqual(text.code, EXIT_REPOSITORY)
        self.assertEqual(len(self.document(js)["findings"]), 1)

    def test_target_separation(self) -> None:
        with TemporaryDirectory() as one, TemporaryDirectory() as two:
            first = _run_repository(self.repository(one, files=(PROD,)))
            second = _run_repository(self.repository(two))

        self.assertEqual(first.measurement.value.rules[0].finding_count, 1)
        self.assertEqual(second.measurement.value.rules[0].finding_count, 0)
        self.assertNotEqual(
            first.measurement.value.target, second.measurement.value.target
        )


if __name__ == "__main__":
    unittest.main()
