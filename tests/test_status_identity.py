from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "status_identity.py"
EXAMPLE = ROOT / "examples" / "phase-1-4" / "consumer-circleci.yml"


def load_tool():
    spec = importlib.util.spec_from_file_location("status_identity", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load status_identity tool")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StatusIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = load_tool()

    def test_normalize_classic_status(self) -> None:
        item = {
            "context": "ci/circleci: orb-lint",
            "state": "success",
            "target_url": "https://circleci.example/job/1",
            "updated_at": "2026-09-05T01:00:00Z",
            "creator": {"login": "circleci"},
        }
        normalized = self.tool.normalize_status(item)
        self.assertEqual(normalized["type"], "status")
        self.assertEqual(normalized["identity"], "ci/circleci: orb-lint")
        self.assertEqual(normalized["result"], "success")
        self.assertEqual(normalized["provider"], "circleci")

    def test_normalize_completed_check_run(self) -> None:
        item = {
            "name": "orb-lint",
            "status": "completed",
            "conclusion": "failure",
            "details_url": "https://example.test/check/1",
            "completed_at": "2026-09-05T01:00:00Z",
            "app": {"slug": "circleci-checks"},
        }
        normalized = self.tool.normalize_check_run(item)
        self.assertEqual(normalized["type"], "check_run")
        self.assertEqual(normalized["identity"], "orb-lint")
        self.assertEqual(normalized["result"], "failure")
        self.assertEqual(normalized["provider"], "circleci-checks")

    def test_latest_by_identity_uses_newest_observation(self) -> None:
        items = [
            {
                "type": "status",
                "identity": "ci/circleci: orb-lint",
                "result": "pending",
                "timestamp": "2026-09-05T01:00:00Z",
            },
            {
                "type": "status",
                "identity": "ci/circleci: orb-lint",
                "result": "success",
                "timestamp": "2026-09-05T01:05:00Z",
            },
        ]
        latest = self.tool.latest_by_identity(items)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["result"], "success")

    def test_build_evidence_keeps_statuses_and_check_runs_separate(self) -> None:
        evidence = self.tool.build_evidence(
            "example/consumer",
            "abc123",
            [
                {
                    "context": "ci/circleci: lint",
                    "state": "success",
                    "updated_at": "2026-09-05T01:00:00Z",
                    "creator": {"login": "circleci"},
                }
            ],
            [
                {
                    "name": "lint",
                    "status": "completed",
                    "conclusion": "success",
                    "completed_at": "2026-09-05T01:00:00Z",
                    "app": {"slug": "circleci-checks"},
                }
            ],
        )
        self.assertEqual(evidence["counts"]["latest_identities"], 2)
        self.assertEqual(
            {(item["type"], item["identity"]) for item in evidence["identities"]},
            {("status", "ci/circleci: lint"), ("check_run", "lint")},
        )

    def test_compare_evidence_reports_same_identity_across_results(self) -> None:
        success = {
            "repository": "example/consumer",
            "sha": "success-sha",
            "identities": [
                {
                    "type": "status",
                    "identity": "ci/circleci: orb-lint",
                    "result": "success",
                    "provider": "circleci",
                }
            ],
        }
        failure = {
            "repository": "example/consumer",
            "sha": "failure-sha",
            "identities": [
                {
                    "type": "status",
                    "identity": "ci/circleci: orb-lint",
                    "result": "failure",
                    "provider": "circleci",
                }
            ],
        }
        comparison = self.tool.compare_evidence(
            success,
            failure,
            "ci/circleci: orb-lint",
        )
        stable = comparison["stable_identities"]
        self.assertEqual(len(stable), 1)
        self.assertEqual(stable[0]["success_result"], "success")
        self.assertEqual(stable[0]["failure_result"], "failure")
        self.assertTrue(stable[0]["same_provider"])

    def test_consumer_example_uses_production_orb_without_checker_ref(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("orbss/orb-lint@0.0.1", text)
        self.assertNotIn("checker_ref", text)


if __name__ == "__main__":
    unittest.main()
