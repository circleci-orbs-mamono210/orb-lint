#!/usr/bin/env bash
set -euo pipefail

target_path="${ORB_LINT_TARGET_PATH:-.}"
expected_exit_code="${ORB_LINT_EXPECTED_EXIT_CODE:-0}"
expect_install_failure="${ORB_LINT_EXPECT_INSTALL_FAILURE:-0}"

if [[ "${expect_install_failure}" == "1" ]]; then
  echo "orb-lint E2E: install failure was expected; skipping CLI execution"
  exit 0
fi

# Preserve the production behavior exactly: without an E2E expectation,
# return orb-lint's original exit code unchanged.
if [[ "${expected_exit_code}" == "0" ]]; then
  exec orb-lint "${target_path}"
fi

set +e
orb-lint "${target_path}"
actual_exit_code=$?
set -e

if [[ "${actual_exit_code}" -ne "${expected_exit_code}" ]]; then
  printf 'orb-lint E2E: expected exit %s, got %s\n' \
    "${expected_exit_code}" "${actual_exit_code}" >&2
  exit 1
fi

printf 'orb-lint E2E: observed expected exit %s for %s\n' \
  "${actual_exit_code}" "${target_path}"
