#!/usr/bin/env bash
set -euo pipefail

readonly ORB_LINT_REPOSITORY_URL="https://github.com/circleci-orbs-mamono210/orb-lint.git"
checker_ref="${ORB_LINT_CHECKER_REF:-}"

if [[ -z "${checker_ref}" ]]; then
  echo "orb-lint: checker_ref is required" >&2
  exit 2
fi

printf 'Installing orb-lint CLI from ref %s\n' "${checker_ref}"
python -m pip install "git+${ORB_LINT_REPOSITORY_URL}@${checker_ref}"
