"""Phase 3-2 / Redmine #5377: `.orb-lint.yml` parse, validation, normalization."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orb_lint._configuration import (
    CONFIGURATION_FILENAME,
    Configuration,
    load_configuration,
)
from orb_lint.failure import (
    INPUT_CONFIGURATION,
    RULE_PREFIX,
    RepositoryInputError,
)


class ConfigurationLoadTests(unittest.TestCase):
    def _load(self, text: str | None) -> Configuration:
        with TemporaryDirectory() as directory:
            target = Path(directory)
            if text is not None:
                (target / CONFIGURATION_FILENAME).write_text(
                    text, encoding="utf-8"
                )
            return load_configuration(target)

    def _reject(self, text: str) -> RepositoryInputError:
        with self.assertRaises(RepositoryInputError) as caught:
            self._load(text)
        return caught.exception

    def test_missing_file_is_an_empty_configuration(self) -> None:
        self.assertEqual(self._load(None), Configuration())

    def test_empty_file_is_an_empty_configuration(self) -> None:
        self.assertEqual(self._load(""), Configuration())

    def test_absent_ignore_key_is_an_empty_configuration(self) -> None:
        self.assertEqual(self._load("ignore:\n"), Configuration())

    def test_valid_configuration_is_parsed(self) -> None:
        configuration = self._load(
            "ignore:\n"
            "  - rule: ORB-003\n"
            "    reason: repository specific permanent exception\n"
            "\n"
            "  - rule: ORB-017\n"
            "    path: .circleci/test-deploy.yml\n"
            "    reason: development bootstrap only\n"
            "    expires: 2026-12-31\n"
        )

        first, second = configuration.ignores
        self.assertEqual(first.rule_id, "ORB-003")
        self.assertEqual(first.reason, "repository specific permanent exception")
        self.assertIsNone(first.path)
        self.assertIsNone(first.expires)
        self.assertEqual(first.index, 0)

        self.assertEqual(second.rule_id, "ORB-017")
        self.assertEqual(second.path, ".circleci/test-deploy.yml")
        self.assertEqual(second.expires, date(2026, 12, 31))
        self.assertEqual(second.index, 1)

    def test_quoted_expires_is_accepted(self) -> None:
        configuration = self._load(
            "ignore:\n"
            "  - rule: ORB-001\n"
            "    reason: r\n"
            "    expires: '2026-12-31'\n"
        )
        self.assertEqual(configuration.ignores[0].expires, date(2026, 12, 31))

    def test_unknown_rule_identity_is_accepted(self) -> None:
        # Existence is not validated: a repository may carry an ignore for a
        # rule this checker version does not implement yet.
        configuration = self._load(
            "ignore:\n  - rule: ORB-999\n    reason: not implemented yet\n"
        )
        self.assertEqual(configuration.ignores[0].rule_id, "ORB-999")


class ConfigurationRejectionTests(ConfigurationLoadTests):
    def test_invalid_configurations_are_input_002(self) -> None:
        cases = {
            "yaml syntax": "ignore: [\n",
            "not a mapping": "- ignore\n",
            "unknown top-level key": "ignores:\n  - rule: ORB-001\n",
            "ignore not a list": "ignore:\n  rule: ORB-001\n",
            "entry not a mapping": "ignore:\n  - ORB-001\n",
            "missing rule": "ignore:\n  - reason: r\n",
            "missing reason": "ignore:\n  - rule: ORB-001\n",
            "empty reason": "ignore:\n  - rule: ORB-001\n    reason: '  '\n",
            "unknown entry key": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    until: 2026-01-01\n"
            ),
            "bad rule format": "ignore:\n  - rule: orb1\n    reason: r\n",
            "absolute path": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    path: /etc/x.yml\n"
            ),
            "escaping path": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    path: ../x.yml\n"
            ),
            "directory path": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    path: .circleci/\n"
            ),
            "backslash path": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    path: a\\b.yml\n"
            ),
            "empty path": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    path: '  '\n"
            ),
            "bad expires": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n    expires: soon\n"
            ),
            "timestamp expires": (
                "ignore:\n  - rule: ORB-001\n    reason: r\n"
                "    expires: 2026-12-31 10:00:00\n"
            ),
        }

        for label, text in cases.items():
            with self.subTest(case=label):
                error = self._reject(text)
                diagnostic = error.diagnostic
                self.assertEqual(diagnostic.diagnostic_id, INPUT_CONFIGURATION)
                self.assertEqual(diagnostic.path, CONFIGURATION_FILENAME)
                # An unusable configuration is never a policy violation.
                self.assertNotIn(RULE_PREFIX, diagnostic.diagnostic_id)


class PathNormalizationTests(ConfigurationLoadTests):
    def test_leading_dot_slash_is_normalized(self) -> None:
        configuration = self._load(
            "ignore:\n"
            "  - rule: ORB-001\n"
            "    reason: r\n"
            "    path: ./.circleci/config.yml\n"
        )
        self.assertEqual(configuration.ignores[0].path, ".circleci/config.yml")

    def test_interior_dot_segments_are_normalized(self) -> None:
        configuration = self._load(
            "ignore:\n"
            "  - rule: ORB-001\n"
            "    reason: r\n"
            "    path: .circleci/./config.yml\n"
        )
        self.assertEqual(configuration.ignores[0].path, ".circleci/config.yml")

    def test_surrounding_whitespace_is_stripped(self) -> None:
        configuration = self._load(
            "ignore:\n"
            "  - rule: '  ORB-001  '\n"
            "    reason: '  spaced reason  '\n"
        )
        entry = configuration.ignores[0]
        self.assertEqual(entry.rule_id, "ORB-001")
        self.assertEqual(entry.reason, "spaced reason")


if __name__ == "__main__":
    unittest.main()


class PathPatternCharacterTests(ConfigurationLoadTests):
    """Phase 3-2-1 / #5384: ``path`` is exact; pattern characters are rejected.

    Accepting ``*`` as a literal today would make a later pattern field a
    silent reinterpretation of existing files, so the characters are reserved.
    """

    def _entry(self, path: str) -> str:
        return (
            f"ignore:\n"
            f"  - rule: {RULE_PREFIX}001\n"
            f"    path: {path!r}\n"
            f"    reason: r\n"
        )

    def test_glob_like_paths_are_input_002(self) -> None:
        for path in ("src/*.yml", ".circleci/?.yml", "src/[ab].yml", "**/x.yml"):
            with self.subTest(path=path):
                error = self._reject(self._entry(path))
                self.assertEqual(
                    error.diagnostic.diagnostic_id, INPUT_CONFIGURATION
                )
                self.assertIn("exact path", error.diagnostic.message)

    def test_ordinary_punctuation_is_still_accepted(self) -> None:
        configuration = self._load(self._entry("src/@orb.yml"))
        self.assertEqual(configuration.ignores[0].path, "src/@orb.yml")
