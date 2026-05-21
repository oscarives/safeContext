#!/usr/bin/env bash
# rollback.sh — Roll back SafeContext to a previous bundle version
# Usage: ./rollback.sh <previous-bundle.tar.gz>
set -euo pipefail

PREV_BUNDLE="${1:?Usage: $0 <previous-bundle.tar.gz>}"
CURRENT_VERSION=$(docker inspect safecontext-api:current --format '{{.Config.Labels.version}}' 2>/dev/null || echo "unknown")

echo "Rolling back from $CURRENT_VERSION to bundle: $PREV_BUNDLE"
echo ""

# 1. Stop current stack gracefully
echo "Stopping current stack..."
docker compose down --timeout 30

# 2. Load previous images from bundle
echo "Loading previous images..."
BUNDLE_DIR=$(basename "$PREV_BUNDLE" .tar.gz)
tar -xzf "$PREV_BUNDLE" --strip-components=1 -C /tmp/rollback-$$
for img in /tmp/rollback-$$/images/*.tar; do
  docker load -i "$img"
done
rm -rf /tmp/rollback-$$

# 3. Restore previous configuration if backed up
BACKUP_FILE="backups/config-${CURRENT_VERSION}.tar.gz"
if [[ -f "$BACKUP_FILE" ]]; then
  echo "Restoring previous configuration..."
  tar -xzf "$BACKUP_FILE"
fi

# 4. Restart with previous images
echo "Starting previous version..."
docker compose up -d

echo ""
echo "Rollback complete. Verifying health..."
sleep 10
curl -sf http://localhost/health && echo "Health check: PASS" || echo "Health check: FAIL — check logs"
