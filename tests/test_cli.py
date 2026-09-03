from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from orb_lint.cli import main


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


if __name__ == "__main__":
    unittest.main()
