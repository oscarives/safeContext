#!/usr/bin/env bash
# Test: verify that WORM prevents overwrite of locked objects
# Exit 0 = WORM working correctly, Exit 1 = WORM not enforced
set -euo pipefail

MC_ALIAS="local"
BUCKET="${MINIO_BUCKET_ARTIFACTS:-safecontext-artifacts}"
TEST_KEY="worm-test/$(date +%s).txt"

mc alias set "$MC_ALIAS" "${MINIO_URL:-http://minio:9000}" \
  "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" >/dev/null 2>&1

# Upload initial object with retention
echo "original content" | mc pipe "${MC_ALIAS}/${BUCKET}/${TEST_KEY}"
mc retention set GOVERNANCE "1d" "${MC_ALIAS}/${BUCKET}/${TEST_KEY}"

# Attempt to overwrite — should fail
if echo "overwritten" | mc pipe "${MC_ALIAS}/${BUCKET}/${TEST_KEY}" 2>/dev/null; then
  echo "FAIL: WORM did not prevent overwrite"
  exit 1
else
  echo "PASS: WORM correctly prevented overwrite"
  exit 0
fi
