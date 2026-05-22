# Runbook: Key Rotation (KMS)

**Versión**: 1.0.0 · **Sistema**: OpenBao 2.5.4 Transit Engine (fork MPL 2.0, Linux Foundation)
**RTO de rotación**: < 5 minutos sin downtime

## 1. Rotar clave de cifrado MinIO

### Pre-requisitos
- Acceso a Vault con token admin
- MinIO accesible

### Paso 1: Iniciar rotación en Vault
```bash
vault write -f transit/keys/minio-safecontext/rotate
```

### Paso 2: Verificar nueva versión de clave
```bash
vault read transit/keys/minio-safecontext
# Verificar que latest_version incrementó
```

### Paso 3: Re-cifrar artefactos existentes (rewrap)
```bash
# Los artefactos existentes continúan siendo legibles con versión anterior
# Re-cifrado en background (opcional — Vault maneja multi-version)
vault write transit/rewrap/minio-safecontext \
  ciphertext="$(vault write -f transit/encrypt/minio-safecontext \
  plaintext=$(echo -n 'test' | base64) -format=json | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["ciphertext"])')"
```

### Paso 4: Verificar acceso post-rotación
```bash
# Verificar que un artefacto existente sigue siendo legible
docker compose exec minio mc stat local/safecontext-artifacts/<any-object>
```

## 2. Verificación de éxito
- Nuevos artefactos se cifran con clave N
- Artefactos con clave N-1 siguen siendo legibles
- Sin downtime ni errores en logs de MinIO

## 3. Rollback (si hay problemas)
```bash
# Vault mantiene todas las versiones — solo cambiar min_decryption_version
vault write transit/keys/minio-safecontext/config min_decryption_version=1
```
