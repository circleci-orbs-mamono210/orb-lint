from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = ROOT / "src" / "scripts" / "install.sh"

class BootstrapContractTests(unittest.TestCase):
    def test_production_job_defaults_to_matching_release_tag(self) -> None:
        job = (ROOT / "src" / "jobs" / "lint.yml").read_text(encoding="utf-8")
        self.assertIn("checker_ref:", job)
        self.assertIn("default: v0.0.1", job)
        self.assertIn("ORB_LINT_CHECKER_REF: << parameters.checker_ref >>", job)

    def test_test_deploy_uses_current_commit_for_dev_orb_and_cli(self) -> None:
        config = (ROOT / ".circleci" / "test-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("orb-lint: orbss/orb-lint@dev:<<pipeline.git.revision>>", config)
        self.assertIn("checker_ref: << pipeline.git.revision >>", config)

    def test_setup_pipeline_publishes_dev_orb_before_continue(self) -> None:
        config = (ROOT / ".circleci" / "config.yml").read_text(encoding="utf-8")
        self.assertIn("setup: true", config)
        self.assertIn("orb-tools/publish:", config)
        self.assertIn("pub-type: dev", config)
        self.assertIn("orb-tools/continue:", config)
        self.assertIn("- orb-tools/publish", config)

    def test_install_script_uses_exact_requested_ref(self) -> None:
        result, captured = self._run_install(
            "0123456789abcdef0123456789abcdef01234567", 0
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("@0123456789abcdef0123456789abcdef01234567", captured)

    def test_install_failure_does_not_fallback_to_release_tag(self) -> None:
        result, captured = self._run_install("does-not-exist", 23)
        self.assertEqual(result.returncode, 23)
        self.assertIn("@does-not-exist", captured)
        self.assertNotIn("@v0.0.1", captured)

    def test_missing_checker_ref_fails_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.txt"
            fake_python = tmp_path / "python"
            fake_python.write_text(
                '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "${ORB_LINT_TEST_CAPTURE}"\nexit 0\n',
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.pop("ORB_LINT_CHECKER_REF", None)
            env["ORB_LINT_TEST_CAPTURE"] = str(capture)
            env["PATH"] = f"{tmp_path}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(capture.exists())

    def _run_install(self, checker_ref: str, python_returncode: int):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            capture = tmp_path / "capture.txt"
            fake_python = tmp_path / "python"
            fake_python.write_text(
                textwrap.dedent("""\
                #!/usr/bin/env bash
                printf "%s\\n" "$@" > "${ORB_LINT_TEST_CAPTURE}"
                exit "${ORB_LINT_TEST_PYTHON_RC}"
                """),
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env["ORB_LINT_CHECKER_REF"] = checker_ref
            env["ORB_LINT_TEST_CAPTURE"] = str(capture)
            env["ORB_LINT_TEST_PYTHON_RC"] = str(python_returncode)
            env["PATH"] = f"{tmp_path}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(INSTALL_SCRIPT)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False
            )
            captured = capture.read_text(encoding="utf-8") if capture.exists() else ""
            return result, captured

if __name__ == "__main__":
    unittest.main()
