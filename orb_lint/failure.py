"""Public failure model for orb-lint; see docs/failure-model.md.

Phase 3-1 / Redmine #5376, under Phase 3 / #5380.

This module owns the process-level failure semantics: which exit code a run
produces, and which identity namespace classifies a non-rule failure. It does
not own rule detection, measurement, or configuration schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "Diagnostic",
    "EXIT_OK",
    "EXIT_OPERATIONAL",
    "EXIT_REPOSITORY",
    "INPUT_CONFIGURATION",
    "INPUT_UNREADABLE",
    "OperationalError",
    "OrbLintError",
    "RepositoryInputError",
    "Severity",
]


# Severity is introduced here only to separate "exit 0 with warnings" from
# "exit 1 with errors". Promoting rules to error severity is Phase 5 work.
Severity = Literal["warning", "error"]

#: No violation, or warning-severity findings only.
EXIT_OK: Final = 0
#: The repository under inspection is at fault: an error finding, an unusable
#: lint input, or an unusable ``.orb-lint.yml``.
EXIT_REPOSITORY: Final = 1
#: orb-lint itself, or the environment it runs in, could not complete the run.
EXIT_OPERATIONAL: Final = 2

RULE_PREFIX: Final = "ORB-"
INPUT_PREFIX: Final = "INPUT-"

#: A file the lint targets exists but cannot be read or decoded.
INPUT_UNREADABLE: Final = "INPUT-001"
#: ``.orb-lint.yml`` exists but cannot be read, decoded, or validated.
INPUT_CONFIGURATION: Final = "INPUT-002"


@dataclass(frozen=True)
class Diagnostic:
    """A repository input or configuration problem that is not a rule finding.

    A diagnostic never carries an ``ORB-`` identity: policy violations and
    unusable input stay separable at the identity level, not only by message
    text.
    """

    diagnostic_id: str
    # Repository-relative when the problem belongs to a specific file.
    path: str | None
    message: str

    def __post_init__(self) -> None:
        if not self.diagnostic_id.startswith(INPUT_PREFIX):
            raise ValueError(
                f"Diagnostic identity must start with {INPUT_PREFIX!r}: "
                f"{self.diagnostic_id!r}"
            )


class OrbLintError(Exception):
    """Base class for failures orb-lint classifies itself."""


class RepositoryInputError(OrbLintError):
    """Repository-supplied input or configuration cannot be evaluated.

    Raised by the input and configuration boundaries, not by rules. The
    attached diagnostic is what the run reports; the message is human-readable
    context only.
    """

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class OperationalError(OrbLintError):
    """orb-lint itself or its environment could not complete the run.

    Never converted into a finding or a diagnostic: an operational failure is
    not evidence about the repository.
    """


def exit_code(
    *,
    diagnostics: tuple[Diagnostic, ...],
    severities: tuple[Severity, ...],
) -> int:
    """Return the repository-facing exit code for a completed run.

    Operational failures never reach this function; they are classified where
    they are caught, so that an unclassified defect cannot silently be reported
    as a clean repository.
    """

    if diagnostics:
        return EXIT_REPOSITORY
    if any(severity == "error" for severity in severities):
        return EXIT_REPOSITORY
    return EXIT_OK
