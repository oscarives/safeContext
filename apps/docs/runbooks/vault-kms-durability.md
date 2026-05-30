# Runbook · Durabilidad de Vault/OpenBao KMS en producción

**Aplica a**: claves Transit de SafeContext — firma de evidencia
(`safecontext-signing`, ECDSA-P256) y cifrado MinIO SSE (`safecontext-minio`).
**Relacionado**: ADR-014 (F7), ADR-015 (F8), `key-rotation.md`, `dr-airgapped.md`.

---

## Contexto

El stack de desarrollo corre OpenBao en **dev mode** (`openbao server -dev`), que
es **in-memory y arranca des-sellado**. Cualquier `restart` del contenedor `vault`
**borra el motor transit y las claves**. Es aceptable en dev porque:

- El one-shot `vault-init` re-provisiona idempotentemente las claves
  (`docker compose --profile auth up -d vault-init`).
- Por **ADR-015**, la clave pública se archiva con la evidencia
  (`signing_keys` + `verification_public_key_pem` en el export), así que la
  **evidencia ya firmada se verifica offline aunque Vault desaparezca**.

> La durabilidad de Vault en prod es necesaria para **seguir firmando** y **rotar**
> claves — **no** para verificar evidencia histórica (eso lo garantiza ADR-015).

---

## Producción: NO usar dev mode

Sustituir el dev mode por **storage persistente + unseal gestionado**.

### 1. Storage persistente (Integrated Storage / Raft)

```hcl
# vault.hcl
storage "raft" {
  path    = "/openbao/data"
  node_id = "safecontext-1"
}
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_cert_file = "/openbao/tls/server.crt"
  tls_key_file  = "/openbao/tls/server.key"
}
api_addr     = "https://vault:8200"
cluster_addr = "https://vault:8201"
disable_mlock = false
```

Montar `/openbao/data` en un **volumen persistente** (no efímero).

### 2. Inicialización (una vez)

```bash
bao operator init -key-shares=5 -key-threshold=3
# Guardar las 5 unseal keys y el root token en custodia segura (Shamir).
```

### 3. Unseal tras cada arranque

Vault prod arranca **sellado**. Opciones, de menor a mayor automatización:

- **Manual / operado**: `bao operator unseal` con el umbral de claves (procedimiento
  de DR; las claves en custodia repartida).
- **Auto-unseal con HSM/PKCS#11**: para entornos air-gapped sin KMS cloud.
- **Auto-unseal transit**: un segundo Vault "raíz" desellla al de evidencia
  (overhead operativo; sólo si ya hay un Vault confiable).

> Air-gapped (perfil SafeContext): preferir **HSM/PKCS#11** o **unseal operado**.
> Evitar KMS cloud (rompe el aislamiento).

### 4. Provisión de claves (una vez, tras unseal)

```bash
docker compose --profile auth run --rm vault-init   # o ./apps/infra/scripts/init-openbao.sh
```

Crea (idempotente): motor transit, `safecontext-signing` (ECDSA-P256,
`exportable=false`) y `safecontext-minio` (AES-256-GCM).

### 5. Backup / DR

- **Snapshots Raft** periódicos: `bao operator raft snapshot save backup.snap`.
- Incluir el snapshot en el ciclo de backup (ver `dr-airgapped.md`).
- **Archivar la clave pública** de cada versión fuera de Vault (ya ocurre vía
  `signing_keys` en PostgreSQL + en cada export). Esto es la red de seguridad: si
  se pierde Vault entero, la evidencia firmada sigue verificándose con
  `apps/tools/verify_offline.py`.

---

## Rotación de clave (interacción con evidencia)

Ver `key-rotation.md`. Puntos clave para no romper el no-repudio:

1. Rotar crea `vault:vN+1:` — las firmas viejas siguen referenciando su
   `signing_key_version`.
2. La pública de **todas** las versiones queda archivada en `signing_keys`, así que
   `verify_signature` (F7-2) y `verify_offline.py` verifican firmas históricas.
3. **Nunca** borrar versiones de clave mientras exista evidencia que las referencie.

---

## Checklist de verificación

```
□ vault.hcl con storage raft + volumen persistente (no dev mode)
□ init ejecutado; unseal keys + root token en custodia
□ procedimiento de unseal definido (HSM / operado)
□ vault-init ejecutado: transit + safecontext-signing (exportable=false) + safecontext-minio
□ snapshots Raft en el ciclo de backup
□ signing_keys poblada (SELECT count(*) FROM signing_keys ≥ 1)
□ verify_offline.py valida un export real de muestra
```
