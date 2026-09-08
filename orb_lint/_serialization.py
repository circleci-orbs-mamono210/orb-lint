"""Private JSON projection of an execution result; see docs/adr/0014-json-schema-v1.md.

Phase 3-3 / Redmine #5378, under Phase 3 / #5380.

This module projects a private ``_ExecutionResult`` onto public JSON schema
v1. It is the only place that knows both shapes, so that the private result
model and the public schema can change independently. The module and its
functions are not a stable public Python API; the JSON document is the
contract.

It does not own evaluation, ignore matching, measurement, or exit codes.
"""

from __future__ import annotations

import json
from typing import Any, Final, Iterable

from orb_lint import __version__
from orb_lint._execution import _EvaluatedFinding, _ExecutionResult
from orb_lint.failure import Diagnostic

#: Bumped only by a decision record; additive fields do not bump it.
SCHEMA_VERSION: Final = 1


def _project_finding(result: _EvaluatedFinding) -> dict[str, Any]:
    finding = result.finding
    ignore = result.ignore
    # The shape is fixed for every finding: an active finding carries the
    # ignore fields as null rather than omitting them, so consumers never
    # branch on key presence.
    return {
        "rule": finding.rule_id,
        "severity": finding.severity,
        "path": finding.path,
        "line": finding.line,
        "message": finding.message,
        "ignored": ignore is not None,
        "ignore_reason": None if ignore is None else ignore.reason,
        "ignore_expires": (
            None
            if ignore is None or ignore.expires is None
            else ignore.expires.isoformat()
        ),
    }


def _project_diagnostic(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "diagnostic": diagnostic.diagnostic_id,
        "path": diagnostic.path,
        "message": diagnostic.message,
    }


def _finding_key(finding: dict[str, Any]) -> tuple[Any, ...]:
    # Every public field participates, so two documents with the same semantic
    # content serialize identically regardless of internal evaluation order.
    return (
        finding["path"],
        finding["line"],
        finding["rule"],
        finding["severity"],
        finding["message"],
        finding["ignored"],
        finding["ignore_reason"] or "",
        finding["ignore_expires"] or "",
    )


def _diagnostic_key(diagnostic: dict[str, Any]) -> tuple[Any, ...]:
    return (
        diagnostic["path"] or "",
        diagnostic["diagnostic"],
        diagnostic["message"],
    )


def _document(
    results: Iterable[_EvaluatedFinding],
    diagnostics: Iterable[Diagnostic],
) -> dict[str, Any]:
    """Return the schema v1 document as a plain dict.

    Only what the public contract needs is projected. The measurement value
    is deliberately never consulted: its representation is private and must
    not leak into the schema.
    """

    findings = sorted(
        (_project_finding(result) for result in results),
        key=_finding_key,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "findings": findings,
        "diagnostics": sorted(
            (_project_diagnostic(d) for d in diagnostics),
            key=_diagnostic_key,
        ),
    }


def _encode(document: dict[str, Any]) -> str:
    # The whole document is encoded before the caller writes anything, so a
    # failure raises here and leaves stdout empty rather than leaving a partial
    # document behind.
    return json.dumps(
        document, sort_keys=True, indent=2, ensure_ascii=False
    ) + "\n"


def _serialize(execution: _ExecutionResult) -> str:
    """Return the complete JSON document for an execution as one string."""

    return _encode(_document(execution.results, execution.diagnostics))


def _serialize_diagnostics(diagnostics: Iterable[Diagnostic]) -> str:
    """Return a document for a run that produced diagnostics and no findings.

    Used when a repository input failure is raised past the execution
    boundary: the JSON contract is the same as for a run that recorded the
    diagnostic normally.
    """

    return _encode(_document((), diagnostics))
