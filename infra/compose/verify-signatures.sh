#!/usr/bin/env bash
# Verify Cosign signatures before deploying images
# Usage: REGISTRY=ghcr.io/org ./verify-signatures.sh <git-sha>
set -euo pipefail

SHA="${1:?Usage: $0 <git-sha>}"
REGISTRY="${REGISTRY:-ghcr.io/safecontext}"
COMPONENTS=("api" "worker" "ui")
OIDC_ISSUER="https://token.actions.githubusercontent.com"
CERT_IDENTITY_REGEXP="https://github.com/safecontext/safecontext/.*"

echo "Verifying signatures for SHA: $SHA"
echo ""

for component in "${COMPONENTS[@]}"; do
  IMAGE="${REGISTRY}/safecontext-${component}:${SHA}"
  echo -n "  Verifying ${component}... "

  cosign verify \
    --certificate-identity-regexp="${CERT_IDENTITY_REGEXP}" \
    --certificate-oidc-issuer="${OIDC_ISSUER}" \
    "${IMAGE}" > /dev/null 2>&1 \
    && echo "SIGNED" \
    || { echo "FAILED"; exit 1; }

  echo -n "  Verifying SBOM attestation for ${component}... "
  cosign verify-attestation \
    --type spdxjson \
    --certificate-identity-regexp="${CERT_IDENTITY_REGEXP}" \
    --certificate-oidc-issuer="${OIDC_ISSUER}" \
    "${IMAGE}" > /dev/null 2>&1 \
    && echo "ATTESTED" \
    || { echo "MISSING SBOM"; exit 1; }
done

echo ""
echo "All images verified successfully."
