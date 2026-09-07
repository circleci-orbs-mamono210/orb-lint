from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from orb_lint.failure import (
    INPUT_UNREADABLE,
    Diagnostic,
    RepositoryInputError,
    Severity,
)

RULE_ID = "ORB-001"
MESSAGE = "publishing context placeholder must be replaced before production use"
# ORB-001 keeps error severity so that its Phase 1 exit-1 behavior is unchanged.
SEVERITY: Severity = "error"

# Phase 1-1 deliberately limits ORB-001 to the concrete publishing-context
# placeholder observed in existing Orb repositories. It is not a generic
# placeholder detector.
_PUBLISHING_CONTEXT = re.compile(r"<publishing-context>")

_CANDIDATE_ROOT_FILES = (
    Path(".circleci/config.yml"),
    Path(".circleci/config.yaml"),
    Path(".circleci/test-deploy.yml"),
    Path(".circleci/test-deploy.yaml"),
    Path("src/@orb.yml"),
)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int
    message: str
    # Defaulted so existing positional construction stays valid.
    severity: Severity = "error"


def _candidate_files(repository: Path) -> list[Path]:
    files: set[Path] = set()

    for relative in _CANDIDATE_ROOT_FILES:
        path = repository / relative
        if path.is_file():
            files.add(path)

    circleci_dir = repository / ".circleci"
    if circleci_dir.is_dir():
        for suffix in ("*.yml", "*.yaml"):
            files.update(path for path in circleci_dir.rglob(suffix) if path.is_file())

    return sorted(files)


def check_orb001(repository: Path) -> list[Finding]:
    findings: list[Finding] = []

    for path in _candidate_files(repository):
        relative = path.relative_to(repository).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            # Unusable lint input is the repository's problem, but it is not a
            # policy violation: report it as INPUT-001, never as ORB-001.
            raise RepositoryInputError(
                Diagnostic(
                    INPUT_UNREADABLE,
                    relative,
                    f"lint input could not be read: {error.__class__.__name__}",
                )
            ) from error

        for number, line in enumerate(text.splitlines(), start=1):
            if _PUBLISHING_CONTEXT.search(line):
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        path=relative,
                        line=number,
                        message=MESSAGE,
                        severity=SEVERITY,
                    )
                )

    return findings
