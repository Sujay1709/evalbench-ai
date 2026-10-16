#!/usr/bin/env bash
# Smoke-test a running read-only EvalBench demo, locally or after a deploy:
#   scripts/smoke_demo.sh http://127.0.0.1:8000
set -euo pipefail

base="${1:?usage: scripts/smoke_demo.sh BASE_URL}"
base="${base%/}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

liveness=$(curl --silent --show-error --fail "$base/health") || fail "/health did not return 200"
grep -q '"status": *"ok"' <<<"$liveness" || fail "/health body: $liveness"

readiness=$(curl --silent --show-error "$base/health/ready")
grep -q '"demo_data": *"ok"' <<<"$readiness" || fail "/health/ready is not ready: $readiness"

headers=$(curl --silent --show-error --fail --head "$base/") || fail "HEAD / did not return 200"
grep -qi '^x-content-type-options: *nosniff' <<<"$headers" || fail "missing nosniff header"

home=$(curl --silent --show-error --fail "$base/") || fail "/ did not return 200"
grep -q "Inspect a caught regression" <<<"$home" || fail "home page has no featured regression"
link=$(grep -o 'href="/compare?[^"]*"' <<<"$home" | head -n 1 | sed -e 's/^href="//' -e 's/"$//' -e 's/&amp;/\&/g')
[[ "$link" == *change=regressed* ]] || fail "featured link is not a regression report: $link"

report=$(curl --silent --show-error --fail "$base$link") || fail "$link did not return 200"
grep -q "auto-001" <<<"$report" || fail "regression report does not list auto-001"

status=$(curl --silent --output /dev/null --write-out '%{http_code}' --request POST "$base/compare")
[[ "$status" == "403" ]] || fail "POST /compare returned $status, expected 403 in read-only mode"

echo "Demo smoke test passed for $base"
