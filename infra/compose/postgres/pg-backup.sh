#!/usr/bin/env bash
# PostgreSQL backup script — runs inside the postgres container or as a sidecar
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_USER="${POSTGRES_USER:-safecontext_app}"
PG_DB="${POSTGRES_DB:-safecontext}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup to $BACKUP_PATH"

# Base backup (includes WAL)
pg_basebackup \
  -h "$PG_HOST" \
  -U "$PG_USER" \
  -D "$BACKUP_PATH" \
  --format=tar \
  --gzip \
  --checkpoint=fast \
  --wal-method=stream \
  --progress

echo "[$(date)] Backup complete: $BACKUP_PATH"

# Retain only last 7 daily backups
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +7 -exec rm -rf {} + 2>/dev/null || true

echo "[$(date)] Cleanup complete. Current backups:"
ls -la "$BACKUP_DIR"
