"""Phase 3-3 / Redmine #5378: deterministic JSON output contract (schema v1)."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import orb_lint
from orb_lint._configuration import CONFIGURATION_FILENAME, IgnoreRule
from orb_lint._execution import _EvaluatedFinding, _ExecutionResult, _run_repository
from orb_lint._measurement import _Evaluation, _MeasurementResult, _RuleEvaluation
from orb_lint._serialization import (
    SCHEMA_VERSION,
    _document,
    _serialize,
    _serialize_diagnostics,
)
from orb_lint.cli import main
from orb_lint.failure import (
    EXIT_OK,
    EXIT_OPERATIONAL,
    EXIT_REPOSITORY,
    INPUT_CONFIGURATION,
    INPUT_UNREADABLE,
    Diagnostic,
    RepositoryInputError,
)
from orb_lint.rules.orb001 import MESSAGE, RULE_ID, Finding


PLACEHOLDER = "context: <publishing-context>\n"
DEV = ".circleci/test-deploy.yml"
PROD = ".circleci/config.yml"

FIXTURES = Path(__file__).parent / "fixtures" / "orb001"


def _finding(path: str, line: int = 1, rule_id: str = RULE_ID, **kw) -> Finding:
    return Finding(rule_id=rule_id, path=path, line=line, message=MESSAGE, **kw)


def _ignore(reason: str, path: str | None = None, expires: date | None = None):
    return IgnoreRule(
        index=0, rule_id=RULE_ID, reason=reason, path=path, expires=expires
    )


def _execution(
    results=(), diagnostics=(), target: Path = Path("/repo")
) -> _ExecutionResult:
    # A hand-built execution result: the serializer must work from the private
    # result model alone, never from a real filesystem or from measurement.
    evaluation = _Evaluation(target, (_RuleEvaluation(RULE_ID, ()),))
    return _ExecutionResult(
        evaluation,
        _MeasurementResult(None, RuntimeError("measurement is not consulted")),
        tuple(diagnostics),
        tuple(results),
    )


class SchemaShapeTests(unittest.TestCase):
    def test_zero_findings(self) -> None:
        document = _document((), ())
        self.assertEqual(
            document,
            {
                "schema_version": 1,
                "tool_version": orb_lint.__version__,
                "findings": [],
                "diagnostics": [],
            },
        )

    def test_schema_version_is_one(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 1)

    def test_tool_version_is_runtime_package_version(self) -> None:
        # No release string is pinned here: the contract is "whatever the
        # installed package says", and the bump itself is release-gate work.
        with patch("orb_lint._serialization.__version__", "9.9.9-test"):
            self.assertEqual(_document((), ())["tool_version"], "9.9.9-test")
        self.assertEqual(_document((), ())["tool_version"], orb_lint.__version__)

    def test_active_finding_has_null_ignore_fields(self) -> None:
        [finding] = _document((_EvaluatedFinding(_finding(PROD, 8)),), ())[
            "findings"
        ]
        self.assertEqual(
            finding,
            {
                "rule": RULE_ID,
                "severity": "error",
                "path": PROD,
                "line": 8,
                "message": MESSAGE,
                "ignored": False,
                "ignore_reason": None,
                "ignore_expires": None,
            },
        )

    def test_ignored_finding_with_expires(self) -> None:
        result = _EvaluatedFinding(
            _finding(DEV, 8),
            _ignore("development bootstrap only", DEV, date(2026, 12, 31)),
        )
        [finding] = _document((result,), ())["findings"]
        self.assertTrue(finding["ignored"])
        self.assertEqual(finding["ignore_reason"], "development bootstrap only")
        self.assertEqual(finding["ignore_expires"], "2026-12-31")

    def test_ignored_finding_without_expires(self) -> None:
        result = _EvaluatedFinding(_finding(PROD), _ignore("permanent"))
        [finding] = _document((result,), ())["findings"]
        self.assertTrue(finding["ignored"])
        self.assertEqual(finding["ignore_reason"], "permanent")
        self.assertIsNone(finding["ignore_expires"])

    def test_severity_is_carried(self) -> None:
        result = _EvaluatedFinding(_finding(PROD, severity="warning"))
        [finding] = _document((result,), ())["findings"]
        self.assertEqual(finding["severity"], "warning")

    def test_multiple_findings_and_multiple_rules(self) -> None:
        results = (
            _EvaluatedFinding(_finding(PROD, 3)),
            _EvaluatedFinding(_finding(PROD, 1)),
            _EvaluatedFinding(_finding(DEV, 1, rule_id="ORB-002")),
        )
        findings = _document(results, ())["findings"]
        self.assertEqual(len(findings), 3)
        self.assertEqual(
            [(f["path"], f["line"], f["rule"]) for f in findings],
            [(PROD, 1, RULE_ID), (PROD, 3, RULE_ID), (DEV, 1, "ORB-002")],
        )

    def test_diagnostics_are_separate_and_never_findings(self) -> None:
        diagnostic = Diagnostic(INPUT_CONFIGURATION, CONFIGURATION_FILENAME, "bad")
        document = _document((), (diagnostic,))
        self.assertEqual(document["findings"], [])
        self.assertEqual(
            document["diagnostics"],
            [
                {
                    "diagnostic": INPUT_CONFIGURATION,
                    "path": CONFIGURATION_FILENAME,
                    "message": "bad",
                }
            ],
        )
        self.assertNotIn("ORB-", json.dumps(document["diagnostics"]))

    def test_diagnostic_without_path_is_null(self) -> None:
        [diagnostic] = _document((), (Diagnostic(INPUT_UNREADABLE, None, "x"),))[
            "diagnostics"
        ]
        self.assertIsNone(diagnostic["path"])

    def test_measurement_is_not_consulted(self) -> None:
        # The execution above carries a failed measurement on purpose. The
        # serializer must neither read it nor expose it.
        text = _serialize(_execution((_EvaluatedFinding(_finding(PROD)),)))
        self.assertNotIn("measurement", text)
        self.assertNotIn("evaluated", text)


class DeterminismTests(unittest.TestCase):
    def test_repeated_serialization_is_identical(self) -> None:
        execution = _execution(
            (
                _EvaluatedFinding(_finding(PROD, 2)),
                _EvaluatedFinding(_finding(DEV, 1), _ignore("r", DEV)),
            ),
            (Diagnostic(INPUT_UNREADABLE, "a.yml", "m"),),
        )
        self.assertEqual(_serialize(execution), _serialize(execution))

    def test_internal_finding_order_does_not_change_output(self) -> None:
        a = _EvaluatedFinding(_finding(PROD, 2))
        b = _EvaluatedFinding(_finding(DEV, 1), _ignore("r", DEV))
        c = _EvaluatedFinding(_finding(PROD, 1))
        self.assertEqual(
            _serialize(_execution((a, b, c))), _serialize(_execution((c, a, b)))
        )

    def test_internal_diagnostic_order_does_not_change_output(self) -> None:
        x = Diagnostic(INPUT_UNREADABLE, "b.yml", "m")
        y = Diagnostic(INPUT_CONFIGURATION, CONFIGURATION_FILENAME, "m")
        z = Diagnostic(INPUT_UNREADABLE, None, "m")
        self.assertEqual(
            _serialize(_execution((), (x, y, z))),
            _serialize(_execution((), (z, x, y))),
        )

    def test_sort_key_covers_every_public_field(self) -> None:
        # Two findings identical in path/line/rule/severity/message differ only
        # in ignore metadata. They must still order deterministically, so the
        # key has to reach the ignore fields; a partial key would leave their
        # relative order to internal evaluation order.
        f = _finding(PROD, 1)
        active = _EvaluatedFinding(f)
        ignored = _EvaluatedFinding(f, _ignore("r"))
        ignored_later = _EvaluatedFinding(f, _ignore("r", expires=date(2027, 1, 1)))
        forward = _serialize(_execution((active, ignored, ignored_later)))
        backward = _serialize(_execution((ignored_later, ignored, active)))
        self.assertEqual(forward, backward)
        findings = json.loads(forward)["findings"]
        self.assertEqual(
            [(x["ignored"], x["ignore_expires"]) for x in findings],
            [(False, None), (True, None), (True, "2027-01-01")],
        )

    def test_keys_are_sorted(self) -> None:
        text = _serialize(_execution((_EvaluatedFinding(_finding(PROD)),)))
        top = list(json.loads(text).keys())
        self.assertEqual(top, sorted(top))
        finding_keys = list(json.loads(text)["findings"][0].keys())
        self.assertEqual(finding_keys, sorted(finding_keys))


class JsonCliTests(unittest.TestCase):
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

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_default_format_is_text(self) -> None:
        code, out, _ = self._run(str(FIXTURES / "pass"))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "orb-lint: OK\n")

    def test_explicit_text_matches_default(self) -> None:
        _, default, _ = self._run(str(FIXTURES / "fail"))
        _, explicit, _ = self._run(str(FIXTURES / "fail"), "--format", "text")
        self.assertEqual(default, explicit)

    def test_unknown_format_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            self._run(str(FIXTURES / "pass"), "--format", "yaml")

    def test_json_stdout_is_one_document_and_nothing_else(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
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
            code, out, err = self._run(str(target), "--format", "json")

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertEqual(err, "")
        document = json.loads(out)  # would raise if anything else were mixed in
        self.assertNotIn("orb-lint: OK", out)
        self.assertNotIn("  ignored:", out)
        self.assertNotIn("  expires:", out)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["tool_version"], orb_lint.__version__)
        self.assertEqual(
            [(f["path"], f["ignored"], f["ignore_reason"], f["ignore_expires"])
             for f in document["findings"]],
            [
                (PROD, False, None, None),
                (DEV, True, "development bootstrap only", "2026-12-31"),
            ],
        )
        self.assertEqual(document["diagnostics"], [])

    def test_json_clean_repository(self) -> None:
        code, out, err = self._run(str(FIXTURES / "pass"), "--format", "json")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out)["findings"], [])

    def test_json_exit_code_matches_text(self) -> None:
        for fixture in ("pass", "fail"):
            with self.subTest(fixture=fixture):
                text_code, _, _ = self._run(str(FIXTURES / fixture))
                json_code, _, _ = self._run(
                    str(FIXTURES / fixture), "--format", "json"
                )
                self.assertEqual(text_code, json_code)

    def test_json_with_input_diagnostic(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory, files=(PROD,), configuration="ignore: [\n"
            )
            code, out, err = self._run(str(target), "--format", "json")

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(f"{CONFIGURATION_FILENAME}: {INPUT_CONFIGURATION}:", err)
        document = json.loads(out)
        self.assertEqual(document["findings"], [])
        self.assertEqual(document["diagnostics"][0]["diagnostic"], INPUT_CONFIGURATION)

    def test_json_operational_failure_writes_nothing_to_stdout(self) -> None:
        failure = OSError("lint input could not be read")
        with patch("orb_lint._execution.check_orb001", side_effect=failure):
            code, out, err = self._run(str(FIXTURES / "pass"), "--format", "json")

        self.assertEqual(code, EXIT_OPERATIONAL)
        self.assertEqual(out, "")
        self.assertIn("operational failure", err)
        self.assertNotIn("INPUT-", err)
        self.assertNotIn("ORB-", err)

    def test_serialization_failure_leaves_no_partial_document(self) -> None:
        # If encoding itself fails, the run is an operational failure and the
        # consumer must find an empty stdout, never a truncated document.
        with patch(
            "orb_lint.cli._serialize", side_effect=TypeError("unencodable")
        ):
            code, out, err = self._run(str(FIXTURES / "fail"), "--format", "json")

        self.assertEqual(code, EXIT_OPERATIONAL)
        self.assertEqual(out, "")
        self.assertIn("operational failure", err)

    def test_defensive_repository_error_path_serialization_failure(self) -> None:
        # The RepositoryInputError handler in main() is a defensive path that
        # the execution boundary normally makes unreachable. It still sits
        # inside the operational boundary: a serialization failure there is
        # exit 2 with an empty stdout, not an unhandled traceback.
        diagnostic = Diagnostic(INPUT_CONFIGURATION, CONFIGURATION_FILENAME, "bad")
        with patch(
            "orb_lint.cli._run_repository",
            side_effect=RepositoryInputError(diagnostic),
        ), patch(
            "orb_lint.cli._serialize_diagnostics",
            side_effect=TypeError("unencodable"),
        ):
            code, out, err = self._run(str(FIXTURES / "pass"), "--format", "json")

        self.assertEqual(code, EXIT_OPERATIONAL)
        self.assertEqual(out, "")
        self.assertIn("operational failure", err)

    def test_defensive_repository_error_path_emits_document(self) -> None:
        # And when serialization succeeds, the defensive path honours the same
        # JSON contract as the normal path: one document, diagnostic on stderr,
        # exit 1.
        diagnostic = Diagnostic(INPUT_CONFIGURATION, CONFIGURATION_FILENAME, "bad")
        with patch(
            "orb_lint.cli._run_repository",
            side_effect=RepositoryInputError(diagnostic),
        ):
            code, out, err = self._run(str(FIXTURES / "pass"), "--format", "json")

        self.assertEqual(code, EXIT_REPOSITORY)
        self.assertIn(f"{INPUT_CONFIGURATION}: bad", err)
        document = json.loads(out)
        self.assertEqual(document["findings"], [])
        self.assertEqual(document["diagnostics"][0]["diagnostic"], INPUT_CONFIGURATION)

    def test_json_repeated_runs_are_identical(self) -> None:
        first = self._run(str(FIXTURES / "fail"), "--format", "json")
        second = self._run(str(FIXTURES / "fail"), "--format", "json")
        self.assertEqual(first, second)

    def test_ignored_only_is_exit_zero_and_visible_in_json(self) -> None:
        with TemporaryDirectory() as directory:
            target = self._repository(
                directory,
                files=(DEV,),
                configuration=(
                    f"ignore:\n  - rule: {RULE_ID}\n    reason: permanent\n"
                ),
            )
            code, out, _ = self._run(str(target), "--format", "json")
            result = _run_repository(target)

        self.assertEqual(code, EXIT_OK)
        [finding] = json.loads(out)["findings"]
        self.assertTrue(finding["ignored"])
        # Still counted by measurement: JSON changes reporting, not evaluation.
        self.assertEqual(result.measurement.value.rules[0].finding_count, 1)


if __name__ == "__main__":
    unittest.main()
