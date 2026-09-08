from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from orb_lint._execution import _run_repository
from orb_lint.failure import (
    EXIT_OPERATIONAL,
    OperationalError,
    RepositoryInputError,
    exit_code,
)


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


def _report_operational(error: BaseException) -> int:
    # Reported on stderr and never as a finding or a diagnostic: an operational
    # failure is a statement about orb-lint, not about the repository.
    print(
        f"orb-lint: operational failure: {error.__class__.__name__}: {error}",
        file=sys.stderr,
    )
    return EXIT_OPERATIONAL


def _ignored_suffix(count: int) -> str:
    if count == 0:
        return ""
    noun = "finding" if count == 1 else "findings"
    return f" ({count} ignored {noun})"


def _run(argv: Sequence[str] | None) -> int:
    args = build_parser().parse_args(argv)
    repository = Path(args.repository).resolve()

    execution = _run_repository(repository)
    findings = execution.active_findings
    ignored = execution.ignored_findings

    # Every finding is printed, in evaluation order. Ignoring suppresses
    # enforcement; it does not hide the finding (Phase 3-2-1 / #5384). A reader
    # must be able to tell a clean repository from an ignored-only one, and see
    # why each suppression exists.
    for result in execution.results:
        finding = result.finding
        print(
            f"{finding.path}:{finding.line}: "
            f"{finding.rule_id}: {finding.message}"
        )
        if result.ignore is not None:
            print(f"  ignored: {result.ignore.reason}")
            if result.ignore.expires is not None:
                print(f"  expires: {result.ignore.expires.isoformat()}")

    for diagnostic in execution.diagnostics:
        location = f"{diagnostic.path}: " if diagnostic.path else ""
        print(
            f"{location}{diagnostic.diagnostic_id}: {diagnostic.message}",
            file=sys.stderr,
        )

    if not findings and not execution.diagnostics:
        # The clean-repository line stays byte-identical to Phase 2. Only the
        # ignored-only case gains a suffix.
        print(f"orb-lint: OK{_ignored_suffix(len(ignored))}")

    # Measurement outcome is deliberately not consulted: a measurement failure
    # must not change the repository-facing result.
    return exit_code(
        diagnostics=execution.diagnostics, severities=execution.severities
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _run(argv)
    except RepositoryInputError as error:
        # Defensive: the execution boundary normally converts these already.
        print(
            f"{error.diagnostic.diagnostic_id}: {error.diagnostic.message}",
            file=sys.stderr,
        )
        return exit_code(diagnostics=(error.diagnostic,), severities=())
    except OperationalError as error:
        return _report_operational(error)
    except Exception as error:  # noqa: BLE001 - unclassified defects are exit 2
        return _report_operational(error)
