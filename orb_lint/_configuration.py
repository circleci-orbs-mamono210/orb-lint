"""Authoritative ``.orb-lint.yml`` contract; see docs/configuration-contract.md.

Phase 3-2 / Redmine #5377, under Phase 3 / #5380.

This module owns every interpretation of ``.orb-lint.yml``: parsing, schema
validation, semantic validation, normalization, ignore matching, and expiry.
It is the single authoritative implementation; a second interpretation of the
same file is a defect, not an optimization.

The module is private (Phase 3-2-1 / #5384). The public contract is the
meaning of ``.orb-lint.yml`` itself, documented in
docs/configuration-contract.md, not this module path or its symbols. When
``orb-lint-audit`` needs the same semantics, Phase 6 will define the narrow
public facade it requires on top of this module; audit must still never
reimplement these semantics.

It does not own rule detection, measurement, or exit codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Final
import re

import yaml

from orb_lint.failure import (
    INPUT_CONFIGURATION,
    RULE_PREFIX,
    Diagnostic,
    RepositoryInputError,
)

__all__ = [
    "CONFIGURATION_FILENAME",
    "Configuration",
    "IgnoreRule",
    "load_configuration",
]

CONFIGURATION_FILENAME: Final = ".orb-lint.yml"

_TOP_LEVEL_KEYS: Final = frozenset({"ignore"})
_IGNORE_KEYS: Final = frozenset({"rule", "reason", "path", "expires"})
_REQUIRED_IGNORE_KEYS: Final = ("rule", "reason")

# Reserved so that a future pattern field can be added without changing the
# meaning of ``path``. See ADR-004.
_PATTERN_CHARACTERS: Final = frozenset("*?[")

# Identity format only. Existence is deliberately not checked: a repository may
# legitimately carry an ignore for a rule this version does not yet implement,
# and rejecting it would couple every consumer's config to the checker version.
_RULE_IDENTITY = re.compile(rf"^{re.escape(RULE_PREFIX)}[0-9]+$")


def _today() -> date:
    """Return the evaluation date in UTC.

    UTC keeps expiry deterministic across CI regions; a repository must not
    expire an ignore at a different moment depending on where it is linted.
    """

    return datetime.now(timezone.utc).date()


def _invalid(message: str) -> RepositoryInputError:
    # Configuration problems are repository input, never a policy violation.
    return RepositoryInputError(
        Diagnostic(INPUT_CONFIGURATION, CONFIGURATION_FILENAME, message)
    )


@dataclass(frozen=True)
class IgnoreRule:
    """One entry of the ``ignore`` list, already validated and normalized."""

    rule_id: str
    reason: str
    # Repository-root-relative POSIX path, or None for a rule-wide ignore.
    path: str | None
    # Inclusive final day on which this entry still applies.
    expires: date | None
    # Position in the configuration file; used for deterministic attribution.
    index: int

    def is_active(self, today: date) -> bool:
        # Inclusive: an ignore expiring today still applies today. There is no
        # grace period beyond that day.
        return self.expires is None or today <= self.expires

    def matches(self, *, rule_id: str, path: str, today: date) -> bool:
        if self.rule_id != rule_id:
            return False
        if self.path is not None and self.path != path:
            return False
        return self.is_active(today)


@dataclass(frozen=True)
class Configuration:
    """A validated configuration. An absent file yields an empty instance."""

    ignores: tuple[IgnoreRule, ...] = ()

    def matching_ignore(
        self, *, rule_id: str, path: str, today: date
    ) -> IgnoreRule | None:
        """Return the first active entry matching this finding, if any.

        Several entries may match. The first one in file order is attributed so
        that the result is deterministic; an expired entry never suppresses a
        finding, and never shadows a later active entry.
        """

        for entry in self.ignores:
            if entry.matches(rule_id=rule_id, path=path, today=today):
                return entry
        return None


def _normalize_path(value: Any, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"ignore[{index}].path must be a nonempty string")

    raw = value.strip()

    if "\\" in raw:
        raise _invalid(
            f"ignore[{index}].path must use forward slashes: {raw!r}"
        )
    if raw.endswith("/"):
        raise _invalid(
            f"ignore[{index}].path must name a file, not a directory: {raw!r}"
        )
    if any(character in raw for character in _PATTERN_CHARACTERS):
        # ``path`` is an exact match (ADR-004). Rejecting pattern characters
        # now keeps the door open for an explicit pattern field later; accepting
        # them as literals would make that addition a silent reinterpretation.
        raise _invalid(
            f"ignore[{index}].path is an exact path and must not contain "
            f"pattern characters (* ? [): {raw!r}"
        )

    pure = PurePosixPath(raw)
    if pure.is_absolute():
        raise _invalid(
            f"ignore[{index}].path must be repository-relative: {raw!r}"
        )

    parts = [part for part in pure.parts if part != "."]
    if not parts:
        raise _invalid(f"ignore[{index}].path must name a file: {raw!r}")
    if ".." in parts:
        # The lint target is one repository. An ignore cannot reach outside it.
        raise _invalid(
            f"ignore[{index}].path must stay inside the repository: {raw!r}"
        )

    return PurePosixPath(*parts).as_posix()


def _normalize_expires(value: Any, index: int) -> date:
    # YAML resolves an unquoted 2026-12-31 to a date; a quoted one stays a
    # string. Both are accepted, nothing else is.
    if isinstance(value, datetime):
        raise _invalid(
            f"ignore[{index}].expires must be a date, not a timestamp"
        )
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as error:
            raise _invalid(
                f"ignore[{index}].expires must be an ISO date "
                f"(YYYY-MM-DD): {value!r}"
            ) from error
    raise _invalid(
        f"ignore[{index}].expires must be an ISO date (YYYY-MM-DD)"
    )


def _build_ignore(entry: Any, index: int) -> IgnoreRule:
    if not isinstance(entry, dict):
        raise _invalid(f"ignore[{index}] must be a mapping")

    keys = set(entry)
    unknown = sorted(keys - _IGNORE_KEYS)
    if unknown:
        raise _invalid(
            f"ignore[{index}] has unknown key(s): {', '.join(unknown)}"
        )

    for required in _REQUIRED_IGNORE_KEYS:
        if required not in keys:
            raise _invalid(f"ignore[{index}] is missing required key {required!r}")

    rule_id = entry["rule"]
    if not isinstance(rule_id, str) or not _RULE_IDENTITY.match(rule_id.strip()):
        raise _invalid(
            f"ignore[{index}].rule must be a rule identity "
            f"like {RULE_PREFIX}001: {rule_id!r}"
        )

    reason = entry["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise _invalid(
            f"ignore[{index}].reason must be a nonempty string"
        )

    path = entry.get("path")
    expires = entry.get("expires")

    return IgnoreRule(
        rule_id=rule_id.strip(),
        reason=reason.strip(),
        path=None if path is None else _normalize_path(path, index),
        expires=None if expires is None else _normalize_expires(expires, index),
        index=index,
    )


def _build(document: Any) -> Configuration:
    if document is None:
        # An empty file is a valid configuration that ignores nothing.
        return Configuration()

    if not isinstance(document, dict):
        raise _invalid("configuration must be a mapping")

    unknown = sorted(set(document) - _TOP_LEVEL_KEYS)
    if unknown:
        raise _invalid(f"unknown top-level key(s): {', '.join(unknown)}")

    entries = document.get("ignore")
    if entries is None:
        return Configuration()
    if not isinstance(entries, list):
        raise _invalid("ignore must be a list")

    return Configuration(
        tuple(_build_ignore(entry, index) for index, entry in enumerate(entries))
    )


def load_configuration(repository: Path) -> Configuration:
    """Load and validate ``.orb-lint.yml`` from a repository root.

    A missing file is not a failure. Any unusable file raises
    ``RepositoryInputError`` carrying an ``INPUT-002`` diagnostic, so an invalid
    configuration can never be reported as a rule violation.
    """

    path = repository / CONFIGURATION_FILENAME

    if not path.exists():
        return Configuration()

    if not path.is_file():
        raise _invalid("configuration path is not a regular file")

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _invalid(
            f"configuration file could not be read: {error.__class__.__name__}"
        ) from error

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise _invalid(
            f"configuration file is not valid YAML: {error.__class__.__name__}"
        ) from error

    return _build(document)
