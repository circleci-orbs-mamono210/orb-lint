#!/usr/bin/env bash
set -euo pipefail

readonly ORB_LINT_REPOSITORY_URL="https://github.com/circleci-orbs-mamono210/orb-lint.git"
checker_ref="${ORB_LINT_CHECKER_REF:-}"
expect_install_failure="${ORB_LINT_EXPECT_INSTALL_FAILURE:-0}"

if [[ -z "${checker_ref}" ]]; then
  echo "orb-lint: checker_ref is required" >&2
  exit 2
fi

printf 'Installing orb-lint CLI from ref %s\n' "${checker_ref}"

if [[ "${expect_install_failure}" != "1" ]]; then
  exec python -m pip install "git+${ORB_LINT_REPOSITORY_URL}@${checker_ref}"
fi

set +e
python -m pip install "git+${ORB_LINT_REPOSITORY_URL}@${checker_ref}"
install_status=$?
set -e

if [[ "${install_status}" -eq 0 ]]; then
  echo "orb-lint E2E: expected CLI install to fail, but it succeeded" >&2
  exit 1
fi

printf 'orb-lint E2E: observed expected CLI install failure (exit %s)\n' \
  "${install_status}"
