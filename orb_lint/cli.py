from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from orb_lint._execution import _run_repository


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

    execution = _run_repository(repository)
    findings = execution.evaluation.findings
    if not findings:
        print("orb-lint: OK")
        return 0

    for finding in findings:
        print(
            f"{finding.path}:{finding.line}: "
            f"{finding.rule_id}: {finding.message}"
        )
    return 1
