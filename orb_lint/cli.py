from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from orb_lint._execution import _ExecutionResult, _run_repository
from orb_lint._serialization import _serialize, _serialize_diagnostics
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
    # A format selector rather than a --json flag, so that a later format can
    # be added without breaking the existing CLI (Phase 3-3 / #5378).
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format on stdout (default: text).",
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


def _print_diagnostics(diagnostics) -> None:
    # Diagnostics go to stderr in every format: they are for the reader of the
    # CI log, and keeping them off stdout is what makes JSON mode parseable.
    for diagnostic in diagnostics:
        location = f"{diagnostic.path}: " if diagnostic.path else ""
        print(
            f"{location}{diagnostic.diagnostic_id}: {diagnostic.message}",
            file=sys.stderr,
        )


def _report_text(execution: _ExecutionResult) -> None:
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

    _print_diagnostics(execution.diagnostics)

    if not findings and not execution.diagnostics:
        # The clean-repository line stays byte-identical to Phase 2. Only the
        # ignored-only case gains a suffix.
        print(f"orb-lint: OK{_ignored_suffix(len(ignored))}")


def _report_json(execution: _ExecutionResult) -> None:
    # Serialize first, write once. If serialization raises, nothing has been
    # written and the failure surfaces as exit 2 with an empty stdout, so a
    # consumer never parses a partial document.
    document = _serialize(execution)
    _print_diagnostics(execution.diagnostics)
    sys.stdout.write(document)


def _run(args: argparse.Namespace) -> int:
    repository = Path(args.repository).resolve()

    execution = _run_repository(repository)

    if args.format == "json":
        _report_json(execution)
    else:
        _report_text(execution)

    # Measurement outcome is deliberately not consulted: a measurement failure
    # must not change the repository-facing result.
    return exit_code(
        diagnostics=execution.diagnostics, severities=execution.severities
    )


def _report_repository_error(
    error: RepositoryInputError, output_format: str
) -> int:
    # Defensive: the execution boundary normally converts these already. The
    # contract is the same as the normal path: the diagnostic goes to stderr
    # in every format, and JSON mode still emits one complete document.
    document = (
        _serialize_diagnostics((error.diagnostic,))
        if output_format == "json"
        else None
    )
    _print_diagnostics((error.diagnostic,))
    if document is not None:
        sys.stdout.write(document)
    return exit_code(diagnostics=(error.diagnostic,), severities=())


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # Both the run and the repository-error report sit inside one
        # operational boundary, so a serialization failure on either path is
        # exit 2 with an empty stdout (ADR-014), never an unhandled traceback.
        try:
            return _run(args)
        except RepositoryInputError as error:
            return _report_repository_error(error, args.format)
    except OperationalError as error:
        return _report_operational(error)
    except Exception as error:  # noqa: BLE001 - unclassified defects are exit 2
        return _report_operational(error)
