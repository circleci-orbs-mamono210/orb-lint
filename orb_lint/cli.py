from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from orb_lint.rules.orb001 import check_orb001


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orb-lint",
        description="Check mamono210 CircleCI Orb repository policies.",
    )
    parser.add_argument(
        "repository",
        nargs="?",
        default=".",
        help="Repository root to inspect (default: current directory).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = Path(args.repository).resolve()

    findings = check_orb001(repository)
    if not findings:
        print("orb-lint: OK")
        return 0

    for finding in findings:
        print(
            f"{finding.path}:{finding.line}: "
            f"{finding.rule_id}: {finding.message}"
        )
    return 1
