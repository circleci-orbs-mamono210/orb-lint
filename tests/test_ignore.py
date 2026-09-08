"""Phase 3-2 / Redmine #5377: ignore scoping and expiry semantics."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orb_lint._execution import _run_repository
from orb_lint.cli import main
from orb_lint._configuration import CONFIGURATION_FILENAME
from orb_lint.failure import EXIT_OK, EXIT_REPOSITORY
from orb_lint.rules.orb001 import MESSAGE, RULE_ID


PLACEHOLDER = "context: <publishing-context>\n"

DEV = ".circleci/test-deploy.yml"
PROD = ".circleci/config.yml"


class IgnoreTestCase(unittest.TestCase):
    def _repository(self, directory: str, *, files, configuration=None) -> Path:
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

    def _run(self, target: Path) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(target)])
        return code, out.getvalue(), err.getvalue()


class RuleLevelIgnoreTests(IgnoreTestCase):
    def test_rule_level_ignore_suppresses_every_path(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(DEV, PROD),
                configuration=(
                    f"ignore:\n  - rule: {RULE_ID}\n    reason: permanent\n"
                ),
            )
            code, out, err = self._run(target)

        self.assertEqual(code, EXIT_OK)
        # Ignored findings stay visible (#5384): suppression is not deletion.
        self.assertEqual(
            out,
            f"{PROD}:1: {RULE_ID}: {MESSAGE}\n"
            f"  ignored: permanent\n"
            f"{DEV}:1: {RULE_ID}: {MESSAGE}\n"
            f"  ignored: permanent\n"
            f"orb-lint: OK (2 ignored findings)\n",
        )
        self.assertEqual(err, "")

    def test_ignoring_another_rule_leaves_this_rule_active(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(PROD,),
                configuration=(
                    "ignore:\n  - rule: ORB-999\n    reason: unrelated\n"
                ),
            )
            code, out, _ = self._run(target)

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(RULE_ID, out)


class PathScopedIgnoreTests(IgnoreTestCase):
    def _development_exception(self, directory: str) -> Path:
        return self._repository(
            directory,
            files=(DEV, PROD),
            configuration=(
                f"ignore:\n"
                f"  - rule: {RULE_ID}\n"
                f"    path: {DEV}\n"
                f"    reason: development bootstrap only\n"
            ),
        )

    def test_path_scoped_ignore_suppresses_only_that_path(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._development_exception(directory)
            code, out, _ = self._run(target)

        self.assertEqual(code, EXIT_REPOSITORY)
        # The active finding is printed as before; the ignored one is printed
        # too, but marked, and it does not earn the OK line.
        self.assertEqual(
            out,
            f"{PROD}:1: {RULE_ID}: {MESSAGE}\n"
            f"{DEV}:1: {RULE_ID}: {MESSAGE}\n"
            f"  ignored: development bootstrap only\n",
        )
        self.assertNotIn("orb-lint: OK", out)

    def test_production_config_keeps_the_same_rule_active(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._development_exception(directory)
            result = _run_repository(target)

        ignored = result.ignored_findings
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored[0].finding.path, DEV)
        self.assertEqual(ignored[0].ignore.reason, "development bootstrap only")
        self.assertEqual(
            tuple(finding.path for finding in result.active_findings), (PROD,)
        )

    def test_path_scoped_ignore_alone_leaves_a_clean_repository(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(DEV,),
                configuration=(
                    f"ignore:\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    path: {DEV}\n"
                    f"    reason: development bootstrap only\n"
                ),
            )
            code, out, _ = self._run(target)

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(
            out,
            f"{DEV}:1: {RULE_ID}: {MESSAGE}\n"
            f"  ignored: development bootstrap only\n"
            f"orb-lint: OK (1 ignored finding)\n",
        )


class ExpiryTests(IgnoreTestCase):
    def _with_expiry(self, directory: str, expires: date) -> Path:
        return self._repository(
            directory,
            files=(PROD,),
            configuration=(
                f"ignore:\n"
                f"  - rule: {RULE_ID}\n"
                f"    reason: temporary\n"
                f"    expires: {expires.isoformat()}\n"
            ),
        )

    def _run_on(self, target: Path, today: date) -> tuple[int, str, str]:
        with patch("orb_lint._execution._today", return_value=today):
            return self._run(target)

    def test_ignore_is_active_before_its_expiry(self) -> None:
        today = date(2026, 6, 1)
        with TemporaryDirectory() as directory:
            target = self._with_expiry(directory, date(2026, 12, 31))
            code, out, _ = self._run_on(target, today)

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(
            out,
            f"{PROD}:1: {RULE_ID}: {MESSAGE}\n"
            f"  ignored: temporary\n"
            f"  expires: 2026-12-31\n"
            f"orb-lint: OK (1 ignored finding)\n",
        )

    def test_ignore_is_active_on_its_expiry_date(self) -> None:
        expires = date(2026, 12, 31)
        with TemporaryDirectory() as directory:
            target = self._with_expiry(directory, expires)
            code, _, _ = self._run_on(target, expires)

        self.assertEqual(code, EXIT_OK)

    def test_expired_ignore_restores_the_finding_without_grace(self) -> None:
        expires = date(2026, 12, 31)
        with TemporaryDirectory() as directory:
            target = self._with_expiry(directory, expires)
            code, out, _ = self._run_on(target, expires + timedelta(days=1))

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(RULE_ID, out)

    def test_expired_entry_does_not_shadow_a_later_active_entry(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(PROD,),
                configuration=(
                    f"ignore:\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    reason: expired\n"
                    f"    expires: 2020-01-01\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    reason: still valid\n"
                ),
            )
            with patch(
                "orb_lint._execution._today", return_value=date(2026, 6, 1)
            ):
                result = _run_repository(target)

        self.assertEqual(len(result.ignored_findings), 1)
        self.assertEqual(result.ignored_findings[0].ignore.reason, "still valid")

    def test_first_active_match_is_attributed(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(PROD,),
                configuration=(
                    f"ignore:\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    reason: first\n"
                    f"  - rule: {RULE_ID}\n"
                    f"    path: {PROD}\n"
                    f"    reason: second\n"
                ),
            )
            result = _run_repository(target)

        self.assertEqual(result.ignored_findings[0].ignore.reason, "first")
        self.assertEqual(result.ignored_findings[0].ignore.index, 0)


class MeasurementBoundaryTests(IgnoreTestCase):
    def test_ignoring_does_not_erase_the_finding_from_measurement(self) -> None:
        # Phase 2 boundary: measurement observes evaluation, so an ignored
        # finding is still counted. Ignoring suppresses enforcement only.
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(PROD,),
                configuration=(
                    f"ignore:\n  - rule: {RULE_ID}\n    reason: permanent\n"
                ),
            )
            result = _run_repository(target)

        self.assertEqual(result.measurement.outcome, "succeeded")
        self.assertEqual(result.measurement.value.rules[0].finding_count, 1)
        self.assertEqual(result.evaluation.lint_outcome, "violations")
        self.assertEqual(len(result.evaluation.findings), 1)
        self.assertEqual(result.active_findings, ())
        self.assertEqual(len(result.ignored_findings), 1)

    def test_invalid_configuration_is_not_converted_to_a_finding(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(PROD,),
                configuration="ignore:\n  - rule: ORB-001\n",
            )
            code, out, err = self._run(target)

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertEqual(out, "")
        self.assertIn("INPUT-002", err)
        self.assertNotIn(RULE_ID, err)


if __name__ == "__main__":
    unittest.main()


class IgnoredFindingReportingTests(IgnoreTestCase):
    """Phase 3-2-1 / #5384: ignored findings are reported, not hidden."""

    def _ignored_only(self, directory: str) -> Path:
        return self._repository(
            directory,
            files=(DEV,),
            configuration=(
                f"ignore:\n"
                f"  - rule: {RULE_ID}\n"
                f"    path: {DEV}\n"
                f"    reason: development bootstrap only\n"
            ),
        )

    def test_clean_repository_output_is_unchanged(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(directory, files=())
            code, out, err = self._run(target)

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "orb-lint: OK\n")
        self.assertEqual(err, "")

    def test_ignored_only_is_distinguishable_from_clean(self) -> None:
        with TemporaryDirectory() as directory:
            code, out, err = self._run(self._ignored_only(directory))

        self.assertEqual(code, EXIT_OK)
        self.assertNotEqual(out, "orb-lint: OK\n")
        self.assertIn("  ignored: development bootstrap only\n", out)
        self.assertTrue(out.endswith("orb-lint: OK (1 ignored finding)\n"))
        self.assertEqual(err, "")

    def test_ignored_finding_stays_in_measurement(self) -> None:
        with TemporaryDirectory() as directory:
            result = _run_repository(self._ignored_only(directory))

        self.assertEqual(result.active_findings, ())
        self.assertEqual(len(result.ignored_findings), 1)
        rule = next(
            r for r in result.measurement.value.rules if r.rule_id == RULE_ID
        )
        self.assertEqual(rule.finding_count, 1)

    def test_output_is_deterministic_across_runs(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._ignored_only(directory)
            first = self._run(target)
            second = self._run(target)

        self.assertEqual(first, second)
