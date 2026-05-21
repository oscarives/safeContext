#!/usr/bin/env sh
# SafeContext — Generate self-signed TLS certificate for development
# Usage: ./infra/compose/generate-certs.sh
# Outputs: infra/compose/certs/server.crt and infra/compose/certs/server.key

set -e

CERTS_DIR="$(dirname "$0")/certs"
mkdir -p "$CERTS_DIR"

if [ -f "$CERTS_DIR/server.crt" ] && [ -f "$CERTS_DIR/server.key" ]; then
    echo "[certs] Certificates already exist at $CERTS_DIR — skipping generation."
    echo "        Delete them and re-run this script to regenerate."
    exit 0
fi

echo "[certs] Generating self-signed TLS certificate (dev only)..."

openssl req -x509 \
    -nodes \
    -newkey rsa:2048 \
    -days 365 \
    -keyout "$CERTS_DIR/server.key" \
    -out    "$CERTS_DIR/server.crt" \
    -subj   "/C=US/ST=Dev/L=Dev/O=SafeContext/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 "$CERTS_DIR/server.key"
chmod 644 "$CERTS_DIR/server.crt"

echo "[certs] Done. Certificate written to $CERTS_DIR/"
echo "        server.crt — public certificate"
echo "        server.key — private key (keep secret)"
