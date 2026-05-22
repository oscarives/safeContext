#!/usr/bin/env bash
# bundle.sh — Generate autonomous SafeContext deployment bundle
# The bundle contains everything needed to deploy/update without internet.
# Usage: ./apps/infra/scripts/bundle.sh <version>
# Output: ./dist/safecontext-bundle-<version>.tar.gz
set -euo pipefail

VERSION="${1:?Usage: $0 <version>  e.g. 1.0.0}"
BUNDLE_DIR="dist/safecontext-bundle-${VERSION}"
HARBOR_HOST="${HARBOR_HOST:-localhost:5000}"

echo "Building SafeContext bundle v${VERSION}"
mkdir -p "$BUNDLE_DIR"/{images,configs,scripts,docs,policies}

# ── 1. Export Docker images ──────────────────────────────────────────────────
echo "Exporting Docker images..."
IMAGES=(
  "safecontext/safecontext-api:${VERSION}"
  "safecontext/safecontext-worker:${VERSION}"
  "safecontext/safecontext-ui:${VERSION}"
  "postgres:18.4-alpine"
  "redis:7.4-alpine"
  "minio/minio:RELEASE.2025-09-07T16-13-09Z"
  "otel/opentelemetry-collector-contrib:0.122.0"
  "prom/prometheus:v2.55.1"
  "grafana/grafana:11.5.2"
  "nginx:1.28-alpine"
  "quay.io/keycloak/keycloak:26.2.0"
  "hashicorp/vault:1.16.2"
)

for img in "${IMAGES[@]}"; do
  safe_name=$(echo "$img" | tr '/:' '_')
  echo "  Saving $img..."
  docker save "$img" -o "${BUNDLE_DIR}/images/${safe_name}.tar"
done

# ── 2. Copy configuration files ──────────────────────────────────────────────
echo "Copying configuration..."
cp docker-compose.yml "$BUNDLE_DIR/configs/"
cp .env.example "$BUNDLE_DIR/configs/"
cp -r apps/infra/compose/ "$BUNDLE_DIR/configs/infra/"
cp -r apps/infra/k8s/ "$BUNDLE_DIR/configs/k8s/" 2>/dev/null || true

# ── 3. Copy policies ─────────────────────────────────────────────────────────
cp -r apps/policies/ "$BUNDLE_DIR/policies/"

# ── 4. Copy scripts ──────────────────────────────────────────────────────────
cp apps/infra/scripts/install-bundle.sh "$BUNDLE_DIR/scripts/"
cp apps/infra/scripts/rollback.sh "$BUNDLE_DIR/scripts/"

# ── 5. Copy documentation ────────────────────────────────────────────────────
cp apps/docs/runbooks/airgapped-install.md "$BUNDLE_DIR/docs/"
cp apps/docs/runbooks/airgapped-update.md "$BUNDLE_DIR/docs/"

# ── 6. Write bundle manifest ─────────────────────────────────────────────────
cat > "$BUNDLE_DIR/MANIFEST.json" << EOF
{
  "version": "${VERSION}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "images": $(printf '%s\n' "${IMAGES[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin]))"),
  "sha256": "TBD"
}
EOF

# ── 7. Create tarball ────────────────────────────────────────────────────────
mkdir -p dist
tar -czf "dist/safecontext-bundle-${VERSION}.tar.gz" -C dist "safecontext-bundle-${VERSION}"

# Update SHA256
SHA=$(sha256sum "dist/safecontext-bundle-${VERSION}.tar.gz" | cut -d' ' -f1)
python3 -c "
import json
with open('${BUNDLE_DIR}/MANIFEST.json') as f: d = json.load(f)
d['sha256'] = '${SHA}'
with open('${BUNDLE_DIR}/MANIFEST.json','w') as f: json.dump(d, f, indent=2)
"

echo ""
echo "Bundle created: dist/safecontext-bundle-${VERSION}.tar.gz"
echo "SHA256: $SHA"
echo "Size: $(du -sh dist/safecontext-bundle-${VERSION}.tar.gz | cut -f1)"
