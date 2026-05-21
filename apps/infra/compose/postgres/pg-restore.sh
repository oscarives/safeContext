#!/usr/bin/env bash
# PostgreSQL restore script
# Usage: ./pg-restore.sh <backup_timestamp>
# Example: ./pg-restore.sh 20260617_030000
set -euo pipefail

BACKUP_TIMESTAMP="${1:?Usage: $0 <backup_timestamp>}"
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_TIMESTAMP}"
PG_DATA="${PGDATA:-/var/lib/postgresql/data}"

if [[ ! -d "$BACKUP_PATH" ]]; then
  echo "ERROR: Backup not found at $BACKUP_PATH"
  exit 1
fi

echo "[$(date)] Starting restore from $BACKUP_PATH"
echo "[$(date)] Target data directory: $PG_DATA"

# Stop PostgreSQL before restore
pg_ctl stop -D "$PG_DATA" -m fast 2>/dev/null || true

# Restore base backup
rm -rf "${PG_DATA:?}"/*
tar -xzf "${BACKUP_PATH}/base.tar.gz" -C "$PG_DATA"

# Restore WAL if present
if [[ -f "${BACKUP_PATH}/pg_wal.tar.gz" ]]; then
  mkdir -p "$PG_DATA/pg_wal"
  tar -xzf "${BACKUP_PATH}/pg_wal.tar.gz" -C "$PG_DATA/pg_wal"
fi

echo "[$(date)] Restore complete. Start PostgreSQL to verify."
