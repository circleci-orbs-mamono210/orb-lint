#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "circleci-orbs-mamono210/orb-lint"
RULESET_NAME = "release-tag-immutability"
API_VERSION = "2026-03-10"
ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "github" / "release-tag-ruleset.json"

COMPARISON_KEYS = (
    "name",
    "target",
    "enforcement",
    "bypass_actors",
    "conditions",
    "rules",
)


def load_manifest() -> dict:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validate_manifest(data)
    return data


def validate_manifest(data: dict) -> None:
    if data.get("name") != RULESET_NAME:
        raise ValueError(f"ruleset name must be {RULESET_NAME!r}")
    if data.get("target") != "tag":
        raise ValueError("ruleset target must be 'tag'")
    if data.get("enforcement") != "active":
        raise ValueError("ruleset enforcement must be 'active'")
    if data.get("bypass_actors") != []:
        raise ValueError("Phase 1-3 baseline requires no bypass actors")

    ref_name = data.get("conditions", {}).get("ref_name", {})
    if ref_name.get("include") != ["refs/tags/v*"]:
        raise ValueError("ruleset must include exactly refs/tags/v*")
    if ref_name.get("exclude") != []:
        raise ValueError("ruleset must not exclude release tags")

    rules = data.get("rules", [])
    rule_types = {rule.get("type") for rule in rules}
    if rule_types != {"update", "deletion"}:
        raise ValueError("ruleset must contain exactly update and deletion rules")

    update_rules = [rule for rule in rules if rule.get("type") == "update"]
    if len(update_rules) != 1:
        raise ValueError("ruleset must contain one update rule")
    params = update_rules[0].get("parameters", {})
    if params.get("update_allows_fetch_and_merge") is not False:
        raise ValueError("update_allows_fetch_and_merge must be false")


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN", "").strip()
    if not value:
        raise RuntimeError(
            "GITHUB_TOKEN is required for remote GitHub ruleset operations"
        )
    return value


def request(method: str, path: str, payload: dict | None = None) -> object:
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token()}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "orb-lint-phase-1-3",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API {method} {path} failed: HTTP {exc.code}: {detail}"
        ) from exc


def list_repository_rulesets() -> list[dict]:
    path = f"/repos/{REPOSITORY}/rulesets?includes_parents=false"
    result = request("GET", path)
    if not isinstance(result, list):
        raise RuntimeError("unexpected ruleset list response")
    return result


def get_ruleset(ruleset_id: int) -> dict:
    result = request("GET", f"/repos/{REPOSITORY}/rulesets/{ruleset_id}")
    if not isinstance(result, dict):
        raise RuntimeError("unexpected ruleset response")
    return result


def find_ruleset() -> dict | None:
    matches = [
        item
        for item in list_repository_rulesets()
        if item.get("name") == RULESET_NAME
        and item.get("source_type") in (None, "Repository")
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"multiple repository rulesets named {RULESET_NAME!r} found"
        )
    if not matches:
        return None
    return get_ruleset(int(matches[0]["id"]))


def normalize_rule(rule: dict) -> dict:
    """Canonicalize GitHub's ruleset response for contract comparison."""
    rule_type = rule.get("type")

    if rule_type == "update":
        parameters = rule.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        return {
            "type": "update",
            "parameters": {
                "update_allows_fetch_and_merge": parameters.get(
                    "update_allows_fetch_and_merge",
                    False,
                )
            },
        }

    if rule_type == "deletion":
        return {"type": "deletion"}

    # Preserve unexpected rules so drift is still detected.
    return dict(rule)


def normalized(data: dict) -> dict:
    result = {key: data.get(key) for key in COMPARISON_KEYS}
    rules = result.get("rules")
    if isinstance(rules, list):
        result["rules"] = [
            normalize_rule(rule) if isinstance(rule, dict) else rule
            for rule in rules
        ]
    return result


def diff_remote(remote: dict | None, desired: dict) -> list[str]:
    if remote is None:
        return ["remote ruleset is missing"]

    differences = []
    actual = normalized(remote)
    expected = normalized(desired)
    for key in COMPARISON_KEYS:
        if actual[key] != expected[key]:
            differences.append(
                f"{key}: expected={expected[key]!r}, actual={actual[key]!r}"
            )
    return differences


def command_validate_local(_: argparse.Namespace) -> int:
    desired = load_manifest()
    print(f"OK: {MANIFEST_PATH.relative_to(ROOT)}")
    print(json.dumps(normalized(desired), indent=2))
    return 0


def command_plan(_: argparse.Namespace) -> int:
    desired = load_manifest()
    remote = find_ruleset()
    differences = diff_remote(remote, desired)
    if not differences:
        print("No change: remote ruleset matches desired state.")
        return 0

    print("Change required:")
    for item in differences:
        print(f"- {item}")
    return 2


def command_verify(_: argparse.Namespace) -> int:
    desired = load_manifest()
    remote = find_ruleset()
    differences = diff_remote(remote, desired)
    if differences:
        print("FAIL: remote ruleset does not match desired state.", file=sys.stderr)
        for item in differences:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("OK: remote release tag ruleset matches desired state.")
    print(f"ruleset_id={remote['id']}")
    return 0


def command_apply(args: argparse.Namespace) -> int:
    desired = load_manifest()
    remote = find_ruleset()
    differences = diff_remote(remote, desired)

    if not differences:
        print("No change: remote ruleset already matches desired state.")
        return 0

    if not args.confirm:
        print(
            "Refusing to change GitHub without --confirm. "
            "Run 'plan' first, then re-run with --confirm.",
            file=sys.stderr,
        )
        return 2

    if remote is None:
        result = request("POST", f"/repos/{REPOSITORY}/rulesets", desired)
        print(f"Created ruleset id={result['id']}.")
    else:
        result = request(
            "PUT",
            f"/repos/{REPOSITORY}/rulesets/{remote['id']}",
            desired,
        )
        print(f"Updated ruleset id={result['id']}.")

    return command_verify(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the Phase 1-3 release-tag ruleset."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    local = sub.add_parser(
        "validate-local",
        help="Validate the checked-in desired-state manifest.",
    )
    local.set_defaults(func=command_validate_local)

    plan = sub.add_parser(
        "plan",
        help="Compare the remote repository ruleset with desired state.",
    )
    plan.set_defaults(func=command_plan)

    verify = sub.add_parser(
        "verify",
        help="Fail unless the remote ruleset exactly matches desired state.",
    )
    verify.set_defaults(func=command_verify)

    apply_parser = sub.add_parser(
        "apply",
        help="Create or update the remote repository ruleset.",
    )
    apply_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement before the remote write.",
    )
    apply_parser.set_defaults(func=command_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
