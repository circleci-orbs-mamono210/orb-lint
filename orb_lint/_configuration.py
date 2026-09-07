"""Configuration boundary for ``.orb-lint.yml``.

Phase 3-1 / Redmine #5376 owns only the failure classification of this
boundary: an unusable configuration file is a repository failure carrying an
``INPUT-002`` diagnostic, never an ``ORB-xxx`` finding.

The schema, ignore semantics, and expiry semantics are Phase 3-2 / #5377. This
module deliberately does not parse YAML yet, so that Phase 3-2 can define the
authoritative parser without first undoing a provisional one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from orb_lint.failure import (
    INPUT_CONFIGURATION,
    Diagnostic,
    RepositoryInputError,
)

CONFIGURATION_FILENAME: Final = ".orb-lint.yml"


def _load_configuration(repository: Path) -> None:
    """Validate that a present configuration file is at least readable.

    Returns ``None``: Phase 3-1 has no configuration model to return. A missing
    file is not a failure.
    """

    path = repository / CONFIGURATION_FILENAME

    if not path.exists():
        return None

    if not path.is_file():
        raise RepositoryInputError(
            Diagnostic(
                INPUT_CONFIGURATION,
                CONFIGURATION_FILENAME,
                "configuration path is not a regular file",
            )
        )

    try:
        path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RepositoryInputError(
            Diagnostic(
                INPUT_CONFIGURATION,
                CONFIGURATION_FILENAME,
                f"configuration file could not be read: {error.__class__.__name__}",
            )
        ) from error

    return None
