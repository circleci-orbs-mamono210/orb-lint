from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT / "src" / "scripts" / "install.sh"
RUN_SCRIPT = ROOT / "src" / "scripts" / "run.sh"


class BootstrapContractTests(unittest.TestCase):
    def test_production_job_defaults_to_matching_release_tag(self) -> None:
        job = (ROOT / "src" / "jobs" / "lint.yml").read_text(encoding="utf-8")

        self.assertIn("checker_ref:", job)
        self.assertIn("default: v0.0.1", job)
        self.assertIn(
            "ORB_LINT_CHECKER_REF: << parameters.checker_ref >>",
            job,
        )
        self.assertIn("command: <<include(scripts/run.sh)>>", job)

    def test_test_deploy_uses_current_commit_for_dev_orb_and_cli(self) -> None:
        config = (ROOT / ".circleci" / "test-deploy.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "orb-lint: orbss/orb-lint@dev:<<pipeline.git.revision>>",
            config,
        )
        self.assertIn(
            "name: bootstrap-current-cli",
            config,
        )
        self.assertIn(
            "checker_ref: << pipeline.git.revision >>",
            config,
        )

    def test_test_deploy_has_orb001_expected_failure_e2e(self) -> None:
        config = (ROOT / ".circleci" / "test-deploy.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: e2e-orb001-expected-failure", config)
        self.assertIn(
            'ORB_LINT_TARGET_PATH="tests/fixtures/orb001/fail"',
            config,
        )
        self.assertIn('ORB_LINT_EXPECTED_EXIT_CODE="1"', config)

    def test_test_deploy_has_invalid_checker_ref_e2e(self) -> None:
        config = (ROOT / ".circleci" / "test-deploy.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: e2e-invalid-checker-ref", config)
        self.assertIn(
            'checker_ref: "0000000000000000000000000000000000000000"',
            config,
        )
        self.assertIn('ORB_LINT_EXPECT_INSTALL_FAILURE="1"', config)

    def test_install_script_uses_exact_requested_ref(self) -> None:
        result, captured = self._run_install(
            checker_ref="0123456789abcdef0123456789abcdef01234567",
            python_returncode=0,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "@0123456789abcdef0123456789abcdef01234567",
            captured,
        )

    def test_install_failure_does_not_fallback_to_release_tag(self) -> None:
        result, captured = self._run_install(
            checker_ref="does-not-exist",
            python_returncode=23,
        )

        self.assertEqual(result.returncode, 23)
        self.assertIn("@does-not-exist", captured)
        self.assertNotIn("@v0.0.1", captured)

    def test_expected_install_failure_is_asserted_as_success(self) -> None:
        result, captured = self._run_install(
            checker_ref="0000000000000000000000000000000000000000",
            python_returncode=23,
            expect_install_failure=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "@0000000000000000000000000000000000000000",
            captured,
        )
        self.assertIn(
            "observed expected CLI install failure",
            result.stdout,
        )

    def test_expected_install_failure_fails_if_install_succeeds(self) -> None:
        result, _ = self._run_install(
            checker_ref="unexpectedly-valid",
            python_returncode=0,
            expect_install_failure=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "expected CLI install to fail, but it succeeded",
            result.stderr,
        )

    def test_missing_checker_ref_fails_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.txt"
            fake_python = tmp_path / "python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$@" > "${ORB_LINT_TEST_CAPTURE}"\n'
                "exit 0\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = os.environ.copy()
            env.pop("ORB_LINT_CHECKER_REF", None)
            env["ORB_LINT_TEST_CAPTURE"] = str(capture)
            env["PATH"] = f"{tmp_path}:{env['PATH']}"

            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertFalse(capture.exists())

    def test_production_run_preserves_orb_lint_exit_code(self) -> None:
        result, captured = self._run_linter(
            orb_lint_returncode=2,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(captured.strip(), ".")

    def test_orb001_expected_failure_is_asserted_as_success(self) -> None:
        result, captured = self._run_linter(
            orb_lint_returncode=1,
            target_path="tests/fixtures/orb001/fail",
            expected_exit_code=1,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            captured.strip(),
            "tests/fixtures/orb001/fail",
        )
        self.assertIn("observed expected exit 1", result.stdout)

    def test_expected_orb_failure_fails_if_linter_passes(self) -> None:
        result, _ = self._run_linter(
            orb_lint_returncode=0,
            target_path="tests/fixtures/orb001/fail",
            expected_exit_code=1,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("expected exit 1, got 0", result.stderr)

    def test_cli_is_skipped_after_expected_install_failure(self) -> None:
        result, captured = self._run_linter(
            orb_lint_returncode=99,
            expect_install_failure=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured, "")
        self.assertIn("skipping CLI execution", result.stdout)

    def _run_install(
        self,
        *,
        checker_ref: str,
        python_returncode: int,
        expect_install_failure: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.txt"
            fake_python = tmp_path / "python"
            fake_python.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf "%s\\n" "$@" > "${ORB_LINT_TEST_CAPTURE}"
                    exit "${ORB_LINT_TEST_PYTHON_RC}"
                    """
                ),
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            env = os.environ.copy()
            env["ORB_LINT_CHECKER_REF"] = checker_ref
            env["ORB_LINT_TEST_CAPTURE"] = str(capture)
            env["ORB_LINT_TEST_PYTHON_RC"] = str(python_returncode)
            env["PATH"] = f"{tmp_path}:{env['PATH']}"
            if expect_install_failure:
                env["ORB_LINT_EXPECT_INSTALL_FAILURE"] = "1"
            else:
                env.pop("ORB_LINT_EXPECT_INSTALL_FAILURE", None)

            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            captured = (
                capture.read_text(encoding="utf-8")
                if capture.exists()
                else ""
            )
            return result, captured

    def _run_linter(
        self,
        *,
        orb_lint_returncode: int,
        target_path: str = ".",
        expected_exit_code: int | None = None,
        expect_install_failure: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.txt"
            fake_orb_lint = tmp_path / "orb-lint"
            fake_orb_lint.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf "%s\\n" "$@" > "${ORB_LINT_TEST_CAPTURE}"
                    exit "${ORB_LINT_TEST_CLI_RC}"
                    """
                ),
                encoding="utf-8",
            )
            fake_orb_lint.chmod(0o755)

            env = os.environ.copy()
            env["ORB_LINT_TEST_CAPTURE"] = str(capture)
            env["ORB_LINT_TEST_CLI_RC"] = str(orb_lint_returncode)
            env["PATH"] = f"{tmp_path}:{env['PATH']}"
            env["ORB_LINT_TARGET_PATH"] = target_path

            if expected_exit_code is None:
                env.pop("ORB_LINT_EXPECTED_EXIT_CODE", None)
            else:
                env["ORB_LINT_EXPECTED_EXIT_CODE"] = str(expected_exit_code)

            if expect_install_failure:
                env["ORB_LINT_EXPECT_INSTALL_FAILURE"] = "1"
            else:
                env.pop("ORB_LINT_EXPECT_INSTALL_FAILURE", None)

            result = subprocess.run(
                ["bash", str(RUN_SCRIPT)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            captured = (
                capture.read_text(encoding="utf-8")
                if capture.exists()
                else ""
            )
            return result, captured


if __name__ == "__main__":
    unittest.main()
