#!/usr/bin/env bash
# install-bundle.sh — Install SafeContext from an offline bundle
# Usage: ./install-bundle.sh <bundle.tar.gz>
set -euo pipefail

BUNDLE_TAR="${1:?Usage: $0 <bundle.tar.gz>}"
BUNDLE_DIR=$(basename "$BUNDLE_TAR" .tar.gz)

echo "Installing SafeContext from bundle: $BUNDLE_TAR"
tar -xzf "$BUNDLE_TAR"

cd "$BUNDLE_DIR"

echo "Loading Docker images (no internet required)..."
for img in images/*.tar; do
  echo "  Loading $img..."
  docker load -i "$img"
done

echo "Configuring environment..."
if [ ! -f .env ]; then
  cp configs/.env.example .env
  echo "  Created .env from template — edit before starting"
fi

echo ""
echo "Next steps:"
echo "  1. Edit .env with your production settings"
echo "  2. docker compose up -d"
echo "  3. Wait for all services to be healthy:"
echo "     docker compose ps"
echo "  4. Apply database migrations (required after first start):"
echo "     docker exec \$(docker compose ps -q api) alembic upgrade head"
echo "  5. (Optional) Initialize OpenBao KMS for MinIO SSE encryption:"
echo "     docker exec \$(docker compose ps -q vault) sh /init-openbao.sh"
echo "  6. Verify deployment:"
echo "     curl http://localhost/health"
echo ""
echo "Installation complete."
