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
cp configs/.env.example .env
echo ""
echo "Edit .env with your settings, then run:"
echo "  docker compose up -d"
echo ""
echo "Installation complete."
