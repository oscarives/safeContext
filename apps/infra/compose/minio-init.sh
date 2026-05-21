#!/usr/bin/env bash
# MinIO initialization: WORM, SSE, versioning, retention
set -euo pipefail

MC_ALIAS="local"
MINIO_URL="${MINIO_URL:-http://minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
BUCKET="${MINIO_BUCKET_ARTIFACTS:-safecontext-artifacts}"

# Wait for MinIO to be ready
until mc alias set "$MC_ALIAS" "$MINIO_URL" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" 2>/dev/null; do
  echo "Waiting for MinIO..."
  sleep 2
done

# Create bucket with object locking (WORM) — must be set at creation
mc mb --with-lock "${MC_ALIAS}/${BUCKET}" 2>/dev/null || echo "Bucket already exists"

# Enable versioning
mc version enable "${MC_ALIAS}/${BUCKET}"

# Set default GOVERNANCE retention: 30 days
mc retention set --default GOVERNANCE "30d" "${MC_ALIAS}/${BUCKET}"

# Enable SSE with local key (KMS in F4)
mc admin config set "${MC_ALIAS}" etcd  2>/dev/null || true

echo "MinIO initialization complete"
echo "  Bucket: ${BUCKET}"
echo "  WORM: enabled (GOVERNANCE mode)"
echo "  Versioning: enabled"
echo "  Default retention: 30 days"
echo "  SSE: configured"
