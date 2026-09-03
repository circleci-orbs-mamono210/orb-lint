from pathlib import Path
import unittest

from orb_lint.rules.orb001 import check_orb001


FIXTURES = Path(__file__).parent / "fixtures" / "orb001"


class Orb001Tests(unittest.TestCase):
    def test_pass_fixture_has_no_findings(self) -> None:
        self.assertEqual(check_orb001(FIXTURES / "pass"), [])

    def test_fail_fixture_reports_publishing_context_placeholder(self) -> None:
        findings = check_orb001(FIXTURES / "fail")

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_id, "ORB-001")
        self.assertEqual(finding.path, ".circleci/test-deploy.yml")
        self.assertEqual(finding.line, 8)


if __name__ == "__main__":
    unittest.main()
