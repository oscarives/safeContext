#!/usr/bin/env bash
# Vault initialization for SafeContext KMS
# Sets up a transit secrets engine for MinIO SSE key management
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
VAULT_TOKEN="${VAULT_DEV_TOKEN:-safecontext-dev-token}"

export VAULT_ADDR VAULT_TOKEN

# Wait for Vault
until vault status >/dev/null 2>&1; do
  echo "Waiting for Vault..."
  sleep 2
done

echo "Configuring Vault transit engine for MinIO KMS..."

# Enable transit secrets engine (KMS)
vault secrets enable transit 2>/dev/null || echo "Transit already enabled"

# Create encryption key for MinIO
vault write -f transit/keys/minio-safecontext type=aes256-gcm96 2>/dev/null \
  || echo "Key already exists"

# Create policy for MinIO to use the key
vault policy write minio-policy - <<EOF
path "transit/encrypt/minio-safecontext" {
  capabilities = ["update"]
}
path "transit/decrypt/minio-safecontext" {
  capabilities = ["update"]
}
path "transit/datakey/plaintext/minio-safecontext" {
  capabilities = ["update"]
}
EOF

# Create token for MinIO with the policy
MINIO_TOKEN=$(vault token create -policy=minio-policy -ttl=720h -format=json | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['auth']['client_token'])")

echo "Vault initialized successfully"
echo "MinIO KMS token: $MINIO_TOKEN"
echo "Store this token as MINIO_KMS_SECRET_KEY in your secrets manager"
