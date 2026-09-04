#!/usr/bin/env bash
set -euo pipefail

repository="${REPOSITORY:-circleci-orbs-mamono210/orb-lint}"
remote="${REMOTE:-origin}"
probe_tag="${1:-}"

if [[ -z "${probe_tag}" ]]; then
  echo "usage: $0 <existing-v*-probe-tag>" >&2
  exit 2
fi

if [[ "${probe_tag}" != v* ]]; then
  echo "probe tag must match v*" >&2
  exit 2
fi

if [[ "${probe_tag}" == "v0.0.1" ]]; then
  echo "refusing to probe the production v0.0.1 tag" >&2
  exit 2
fi

git fetch --tags "${remote}"

if ! git rev-parse -q --verify "refs/tags/${probe_tag}^{commit}" >/dev/null; then
  echo "probe tag ${probe_tag} must already exist before this test" >&2
  exit 2
fi

original_sha="$(git rev-parse "refs/tags/${probe_tag}^{commit}")"
candidate_sha="$(git rev-parse HEAD)"

if [[ "${candidate_sha}" == "${original_sha}" ]]; then
  candidate_sha="$(git rev-parse HEAD^)"
fi

echo "Probing ruleset against ${repository}"
echo "probe_tag=${probe_tag}"
echo "original_sha=${original_sha}"
echo "candidate_sha=${candidate_sha}"

set +e
update_output="$(
  git push --force "${remote}" \
    "${candidate_sha}:refs/tags/${probe_tag}" 2>&1
)"
update_status=$?
set -e

if [[ "${update_status}" -eq 0 ]]; then
  echo "FAIL: protected tag update unexpectedly succeeded" >&2
  echo "${update_output}" >&2
  echo "Manual recovery is required: restore ${probe_tag} to ${original_sha}." >&2
  exit 1
fi

echo "OK: tag update was rejected"

set +e
delete_output="$(
  git push "${remote}" ":refs/tags/${probe_tag}" 2>&1
)"
delete_status=$?
set -e

if [[ "${delete_status}" -eq 0 ]]; then
  echo "FAIL: protected tag deletion unexpectedly succeeded" >&2
  echo "${delete_output}" >&2
  echo "Manual recovery is required: recreate ${probe_tag} at ${original_sha}." >&2
  exit 1
fi

echo "OK: tag deletion was rejected"
echo "PASS: update and deletion are both protected"
