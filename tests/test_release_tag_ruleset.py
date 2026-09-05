from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "github" / "release-tag-ruleset.json"
TOOL = ROOT / "tools" / "github_ruleset.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("github_ruleset", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load github_ruleset tool")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTagRulesetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_targets_v_tags(self) -> None:
        self.assertEqual(self.manifest["target"], "tag")
        self.assertEqual(
            self.manifest["conditions"]["ref_name"]["include"],
            ["refs/tags/v*"],
        )
        self.assertEqual(
            self.manifest["conditions"]["ref_name"]["exclude"],
            [],
        )

    def test_ruleset_is_active(self) -> None:
        self.assertEqual(self.manifest["enforcement"], "active")

    def test_no_bypass_actors_in_phase_1_baseline(self) -> None:
        self.assertEqual(self.manifest["bypass_actors"], [])

    def test_only_update_and_deletion_are_restricted(self) -> None:
        rule_types = {rule["type"] for rule in self.manifest["rules"]}
        self.assertEqual(rule_types, {"update", "deletion"})
        self.assertNotIn("creation", rule_types)

    def test_update_rule_does_not_allow_fetch_and_merge(self) -> None:
        update = next(
            rule
            for rule in self.manifest["rules"]
            if rule["type"] == "update"
        )
        self.assertIs(
            update["parameters"]["update_allows_fetch_and_merge"],
            False,
        )

    def test_management_tool_accepts_manifest(self) -> None:
        tool = load_tool()
        tool.validate_manifest(self.manifest)

    def test_management_tool_detects_missing_remote(self) -> None:
        tool = load_tool()
        self.assertEqual(
            tool.diff_remote(None, self.manifest),
            ["remote ruleset is missing"],
        )

    def test_remote_omitted_update_parameters_match_false(self) -> None:
        tool = load_tool()
        remote = {
            key: self.manifest[key]
            for key in tool.COMPARISON_KEYS
        }
        remote["rules"] = [
            {"type": "update"},
            {"type": "deletion"},
        ]
        self.assertEqual(tool.diff_remote(remote, self.manifest), [])

    def test_remote_explicit_false_update_parameter_matches(self) -> None:
        tool = load_tool()
        remote = {
            key: self.manifest[key]
            for key in tool.COMPARISON_KEYS
        }
        remote["rules"] = [
            {
                "type": "update",
                "parameters": {
                    "update_allows_fetch_and_merge": False,
                },
            },
            {"type": "deletion"},
        ]
        self.assertEqual(tool.diff_remote(remote, self.manifest), [])

    def test_remote_true_update_parameter_is_detected_as_drift(self) -> None:
        tool = load_tool()
        remote = {
            key: self.manifest[key]
            for key in tool.COMPARISON_KEYS
        }
        remote["rules"] = [
            {
                "type": "update",
                "parameters": {
                    "update_allows_fetch_and_merge": True,
                },
            },
            {"type": "deletion"},
        ]
        differences = tool.diff_remote(remote, self.manifest)
        self.assertEqual(len(differences), 1)
        self.assertTrue(differences[0].startswith("rules:"))

    def test_unknown_remote_rule_is_not_normalized_away(self) -> None:
        tool = load_tool()
        remote = {
            key: self.manifest[key]
            for key in tool.COMPARISON_KEYS
        }
        remote["rules"] = [
            {"type": "update"},
            {"type": "deletion"},
            {"type": "creation"},
        ]
        differences = tool.diff_remote(remote, self.manifest)
        self.assertEqual(len(differences), 1)
        self.assertTrue(differences[0].startswith("rules:"))


if __name__ == "__main__":
    unittest.main()
