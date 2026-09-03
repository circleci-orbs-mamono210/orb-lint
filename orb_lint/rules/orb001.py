from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

RULE_ID = "ORB-001"
MESSAGE = "publishing context placeholder must be replaced before production use"

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
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if _PUBLISHING_CONTEXT.search(line):
                findings.append(
                    Finding(
                        rule_id=RULE_ID,
                        path=path.relative_to(repository).as_posix(),
                        line=number,
                        message=MESSAGE,
                    )
                )

    return findings
