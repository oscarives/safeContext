#!/usr/bin/env bash
# MinIO backup — mirrors artifacts bucket to a backup bucket
set -euo pipefail

SOURCE="${MINIO_BUCKET_ARTIFACTS:-safecontext-artifacts}"
BACKUP_BUCKET="${MINIO_BUCKET_BACKUP:-safecontext-artifacts-backup}"
MC_ALIAS="local"

mc alias set "$MC_ALIAS" "${MINIO_URL:-http://minio:9000}" \
  "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null 2>&1

# Create backup bucket if not exists (no WORM on backup)
mc mb "${MC_ALIAS}/${BACKUP_BUCKET}" 2>/dev/null || true

# Mirror: sync all objects from source to backup
mc mirror --overwrite "${MC_ALIAS}/${SOURCE}" "${MC_ALIAS}/${BACKUP_BUCKET}"

echo "[$(date)] MinIO mirror complete: ${SOURCE} → ${BACKUP_BUCKET}"
