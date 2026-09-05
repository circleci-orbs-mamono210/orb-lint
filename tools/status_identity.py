#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
USER_AGENT = "orb-lint-phase-1-4-status-identity"


def github_get_json(path: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(f"{API_ROOT}{path}", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API GET {path} failed: HTTP {exc.code}: {body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API GET {path} failed: {exc}") from exc


def normalize_status(item: dict[str, Any]) -> dict[str, Any]:
    creator = item.get("creator") or {}
    return {
        "type": "status",
        "identity": item.get("context") or "",
        "result": item.get("state") or "",
        "provider": creator.get("login"),
        "url": item.get("target_url"),
        "timestamp": item.get("updated_at") or item.get("created_at"),
    }


def normalize_check_run(item: dict[str, Any]) -> dict[str, Any]:
    app = item.get("app") or {}
    status = item.get("status") or ""
    conclusion = item.get("conclusion")
    result = conclusion if status == "completed" and conclusion else status
    return {
        "type": "check_run",
        "identity": item.get("name") or "",
        "result": result,
        "provider": app.get("slug") or app.get("name"),
        "url": item.get("details_url") or item.get("html_url"),
        "timestamp": (
            item.get("completed_at")
            or item.get("started_at")
            or item.get("updated_at")
            or item.get("created_at")
        ),
    }


def latest_by_identity(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        identity = item.get("identity") or ""
        if not identity:
            continue
        key = (item.get("type") or "", identity)
        current = latest.get(key)
        if current is None:
            latest[key] = item
            continue
        current_time = current.get("timestamp") or ""
        item_time = item.get("timestamp") or ""
        if item_time >= current_time:
            latest[key] = item
    return sorted(
        latest.values(),
        key=lambda item: (item.get("type") or "", item.get("identity") or ""),
    )


def build_evidence(
    repository: str,
    sha: str,
    statuses: list[dict[str, Any]],
    check_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = [normalize_status(item) for item in statuses]
    normalized.extend(normalize_check_run(item) for item in check_runs)
    identities = latest_by_identity(normalized)
    return {
        "schema_version": 1,
        "repository": repository,
        "sha": sha,
        "identities": identities,
        "counts": {
            "statuses_received": len(statuses),
            "check_runs_received": len(check_runs),
            "latest_identities": len(identities),
        },
    }


def collect_evidence(repository: str, sha: str, token: str | None) -> dict[str, Any]:
    if repository.count("/") != 1:
        raise ValueError("repository must be in owner/name form")
    owner, name = repository.split("/", 1)
    repo_path = f"{quote(owner, safe='')}/{quote(name, safe='')}"
    ref = quote(sha, safe="")

    statuses_payload = github_get_json(
        f"/repos/{repo_path}/commits/{ref}/statuses?per_page=100",
        token,
    )
    checks_payload = github_get_json(
        f"/repos/{repo_path}/commits/{ref}/check-runs?per_page=100",
        token,
    )
    if not isinstance(statuses_payload, list):
        raise RuntimeError("unexpected GitHub statuses response")
    if not isinstance(checks_payload, dict):
        raise RuntimeError("unexpected GitHub check-runs response")
    check_runs = checks_payload.get("check_runs") or []
    if not isinstance(check_runs, list):
        raise RuntimeError("unexpected GitHub check-runs payload")
    return build_evidence(repository, sha, statuses_payload, check_runs)


def compare_evidence(
    success: dict[str, Any],
    failure: dict[str, Any],
    identity: str | None = None,
) -> dict[str, Any]:
    def index(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for item in payload.get("identities") or []:
            key = (item.get("type") or "", item.get("identity") or "")
            if key[1]:
                result[key] = item
        return result

    success_index = index(success)
    failure_index = index(failure)
    common = sorted(set(success_index) & set(failure_index))
    if identity is not None:
        common = [key for key in common if key[1] == identity]

    stable = []
    for key in common:
        success_item = success_index[key]
        failure_item = failure_index[key]
        stable.append(
            {
                "type": key[0],
                "identity": key[1],
                "success_result": success_item.get("result"),
                "failure_result": failure_item.get("result"),
                "success_provider": success_item.get("provider"),
                "failure_provider": failure_item.get("provider"),
                "same_provider": success_item.get("provider")
                == failure_item.get("provider"),
            }
        )

    return {
        "schema_version": 1,
        "success_repository": success.get("repository"),
        "success_sha": success.get("sha"),
        "failure_repository": failure.get("repository"),
        "failure_sha": failure.get("sha"),
        "requested_identity": identity,
        "stable_identities": stable,
    }


def write_json(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect and compare GitHub status/check identities for the Phase 1-4 "
            "required-status spike. The tool does not guess the orb-lint identity."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="collect statuses and check runs")
    collect.add_argument("--repo", required=True, help="GitHub repository owner/name")
    collect.add_argument("--sha", required=True, help="consumer commit SHA")
    collect.add_argument("--output", help="write JSON evidence to this path")
    collect.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="environment variable containing an optional GitHub token",
    )

    compare = subparsers.add_parser(
        "compare", help="compare success and failure evidence by exact identity"
    )
    compare.add_argument("--success", required=True, help="success evidence JSON")
    compare.add_argument("--failure", required=True, help="failure evidence JSON")
    compare.add_argument(
        "--identity",
        help="optional exact identity to select after measuring it",
    )
    compare.add_argument("--output", help="write comparison JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "collect":
            token = os.environ.get(args.token_env)
            payload = collect_evidence(args.repo, args.sha, token)
            write_json(payload, args.output)
            return 0
        if args.command == "compare":
            payload = compare_evidence(
                load_json(args.success),
                load_json(args.failure),
                args.identity,
            )
            write_json(payload, args.output)
            return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
