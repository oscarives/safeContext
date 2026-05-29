#!/usr/bin/env bash
# init-openbao.sh — Inicializar OpenBao KMS para SafeContext
#
# Configura el motor transit para gestión de claves de cifrado de MinIO SSE.
# Ejecutar UNA VEZ después de que OpenBao esté healthy.
#
# Uso:
#   docker exec safecontext-vault-1 sh /init-openbao.sh
#   # o desde el host si VAULT_ADDR apunta al contenedor:
#   ./apps/infra/scripts/init-openbao.sh
#
# Prerequisitos:
#   - OpenBao corriendo y healthy (ver docker-compose.yml service: vault)
#   - VAULT_ADDR y VAULT_DEV_TOKEN en el entorno (o BAO_TOKEN)

set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
# Debe coincidir con VAULT_DEV_TOKEN del .env (= BAO_DEV_ROOT_TOKEN_ID del compose).
BAO_TOKEN="${VAULT_DEV_TOKEN:-safecontext-dev-vault-token}"

# OpenBao CLI es 'bao'; Vault CLI es 'vault' — intentar ambos
BAO_CMD="bao"
if ! command -v bao &>/dev/null; then
    BAO_CMD="vault"
fi

echo "Inicializando OpenBao KMS en $VAULT_ADDR usando '$BAO_CMD'..."

# ── Motor transit ────────────────────────────────────────────────────────────

VAULT_TOKEN="$BAO_TOKEN" $BAO_CMD secrets enable \
    -address="$VAULT_ADDR" \
    transit 2>/dev/null || echo "  Motor transit ya habilitado"

# ── Clave maestra para MinIO SSE ─────────────────────────────────────────────

VAULT_TOKEN="$BAO_TOKEN" $BAO_CMD write \
    -address="$VAULT_ADDR" \
    transit/keys/safecontext-minio \
    type=aes256-gcm96 2>/dev/null || echo "  Clave safecontext-minio ya existe"

# ── Clave de firma de evidencia (F7 / ADR-014) ───────────────────────────────
# ECDSA-P256 no-exportable: firma write-time del audit trail (no-repudio).
# exportable=false (F7-3/H4) → la clave privada nunca sale de Transit; la pública
# se obtiene de transit/keys para verificación offline. La usan API (read-time
# fallback / anclaje) y worker (auditor_agent, sellado write-time).
VAULT_TOKEN="$BAO_TOKEN" $BAO_CMD write \
    -address="$VAULT_ADDR" -f \
    transit/keys/safecontext-signing \
    type=ecdsa-p256 exportable=false 2>/dev/null \
    || echo "  Clave safecontext-signing ya existe"

# ── Política de acceso mínimo ────────────────────────────────────────────────

VAULT_TOKEN="$BAO_TOKEN" $BAO_CMD policy write \
    -address="$VAULT_ADDR" \
    safecontext-minio-policy - <<'EOF'
# Acceso mínimo para MinIO SSE-KMS: solo encrypt/decrypt de la clave específica
path "transit/encrypt/safecontext-minio" {
  capabilities = ["update"]
}
path "transit/decrypt/safecontext-minio" {
  capabilities = ["update"]
}
EOF

echo ""
echo "OpenBao KMS configurado correctamente:"
echo "  Motor:   transit"
echo "  Clave:   transit/keys/safecontext-minio    (AES256-GCM96, MinIO SSE)"
echo "  Clave:   transit/keys/safecontext-signing  (ECDSA-P256, no-exportable, audit F7)"
echo "  Política: safecontext-minio-policy"
echo ""
echo "Para configurar MinIO SSE-KMS, añadir al entorno de MinIO:"
echo "  MINIO_KMS_KES_ENDPOINT=http://vault:8200"
echo "  MINIO_KMS_KES_KEY_NAME=safecontext-minio"
echo "  MINIO_KMS_KES_CAPATH=/path/to/ca.pem  (si usa TLS)"
echo ""
echo "Verificar:"
echo "  VAULT_TOKEN=$BAO_TOKEN $BAO_CMD list -address=$VAULT_ADDR transit/keys"
