#!/usr/bin/env bash
# sync-images.sh — Pull all required images and push to Harbor registry
# Run this script ONCE while internet is available.
# After this, the stack runs entirely from the local registry.
set -euo pipefail

HARBOR_HOST="${HARBOR_HOST:-localhost:5000}"
HARBOR_USER="${HARBOR_USER:-admin}"
HARBOR_PASS="${HARBOR_PASS:-Harbor12345}"
SHA="${IMAGE_SHA:-latest}"

echo "Logging in to Harbor at $HARBOR_HOST"
docker login "$HARBOR_HOST" -u "$HARBOR_USER" -p "$HARBOR_PASS"

# SafeContext application images (built locally)
APP_IMAGES=(
  "safecontext/safecontext-api:${SHA}"
  "safecontext/safecontext-worker:${SHA}"
  "safecontext/safecontext-ui:${SHA}"
)

# Infrastructure images (pulled from public registries)
INFRA_IMAGES=(
  "postgres:18.4-alpine"
  "redis:7.4-alpine"
  "minio/minio:RELEASE.2025-09-07T16-13-09Z"
  "otel/opentelemetry-collector-contrib:0.122.0"
  "prom/prometheus:v2.55.1"
  "grafana/grafana:11.5.2"
  "nginx:1.28-alpine"
  "quay.io/keycloak/keycloak:26.2.0"
  "hashicorp/vault:1.16.2"
  "minio/mc:latest"
  "goharbor/registry-photon:v2.10.2"
)

echo "Pulling and pushing infrastructure images..."
for img in "${INFRA_IMAGES[@]}"; do
  local_tag="${HARBOR_HOST}/library/${img##*/}"
  echo "  $img -> $local_tag"
  docker pull "$img"
  docker tag "$img" "$local_tag"
  docker push "$local_tag"
done

echo "Pushing SafeContext application images..."
for img in "${APP_IMAGES[@]}"; do
  local_tag="${HARBOR_HOST}/${img}"
  docker tag "$img" "$local_tag"
  docker push "$local_tag"

  # Re-sign for local registry
  if command -v cosign &>/dev/null; then
    cosign copy "ghcr.io/${img}" "${HARBOR_HOST}/${img}" 2>/dev/null || \
      echo "  Note: signature copy requires cosign v2+"
  fi
done

echo ""
echo "All images synced to Harbor at $HARBOR_HOST"
echo "Update IMAGE_REGISTRY in .env to: $HARBOR_HOST"
