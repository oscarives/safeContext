# ADR-015 · Evidencia auto-contenida y verificación offline

**Estado**: Aceptado (ejecutado — F8-1..F8-5 completados 2026-05-29)
**Fecha**: 2026-05-29
**Contexto**: Continuación de ADR-014 (no-repudio del audit trail) — independencia de Vault
**Relacionado**: ADR-014 (F7), ADR-008 (MinIO WORM), F6-B

---

## Contexto

F7 (ADR-014) hizo que cada operación se firme en **write-time** con la clave
asimétrica ECDSA-P256 de Vault Transit, encadenada y anclada. El no-repudio
quedó correcto **mientras Vault está vivo**: la verificación de una firma
necesita la **clave pública**, y hoy ésta se obtiene **en vivo de Vault** en el
momento del audit export (`get_public_key`).

Eso deja tres dependencias implícitas que debilitan el objetivo de "evidencia con
validez legal verificable por un tercero sin confiar en SafeContext":

1. Si Vault está caído al momento del export, `verification_public_key` viene
   vacío → el export no es verificable offline.
2. Si la clave se **rota** o el KMS se **decomisiona**, las firmas históricas
   dejan de poder verificarse (la pública de la versión vieja ya no se sirve).
3. El stack dev de Vault (OpenBao `-dev`) es **in-memory**: un reinicio borra las
   claves. En prod se resuelve con storage persistente, pero la evidencia no
   debería depender de esa decisión operativa.

El insight clave: **la durabilidad de Vault no es el problema central**. Lo que
blinda el objetivo es hacer la **evidencia auto-contenida** — que la clave pública
viaje archivada con la evidencia, de modo que la verificación nunca dependa de
Vault, ni hoy ni dentro de diez años.

---

## Decisión

Archivar la **clave pública** (PEM, por `key_version`) de forma durable y
embeberla en la evidencia exportable, y entregar un **verificador offline
standalone**. Con esto, perder/rotar/apagar Vault deja de invalidar la evidencia
pasada.

1. Tabla `signing_keys` (`key_version` PK → `public_key_pem`, `algorithm`): fuente
   durable, poblada idempotentemente en write-time al firmar (best-effort, una vez
   por versión).
2. El audit export embebe `verification_public_key_pem` resuelto **durable-first**
   (tabla `signing_keys`), con fallback a fetch en vivo sólo para versiones
   legacy/no archivadas.
3. Los `chain_anchors` persisten `signing_public_key_pem` con cada ancla.
4. `apps/tools/verify_offline.py`: recomputa el `operation_hash` canónico desde los
   campos de la operación y verifica la firma ECDSA-P256 con la clave embebida,
   **sin red ni Vault**. También verifica anclas.
5. La **durabilidad de Vault en producción** (Raft + unseal + snapshots) se trata
   como hardening operativo documentado (runbook `vault-kms-durability.md`), no
   como bloqueante: una vez archivada la pública, ya no afecta la evidencia
   histórica.

---

## Hallazgos y estado

Leyenda: `🔲 PENDIENTE` · `🔄 EN CURSO` · `✅ COMPLETADO`

### H1 · La pública se obtiene en vivo de Vault al exportar — 🔴 crítico — ✅ COMPLETADO
Si Vault está caído al exportar, el export no lleva clave → no verificable offline.
**Fix**: tabla `signing_keys` + embeber `verification_public_key_pem` durable-first.

### H2 · Rotación/decomiso de clave rompe verificación histórica — 🔴 crítico — ✅ COMPLETADO
La pública de versiones viejas deja de servirse tras rotar.
**Fix**: archivar la pública **por versión**; toda firma referencia su `key_version`.

### H3 · Sin verificador independiente entregable — 🟡 alto — ✅ COMPLETADO
No existía forma de que un tercero verifique sin la API de SafeContext.
**Fix**: `verify_offline.py` standalone (stdlib + `cryptography`).

### H4 · Vault dev in-memory pierde claves al reiniciar — 🟡 alto — ✅ MITIGADO
Es por diseño de OpenBao `-dev`. **Fix**: una vez archivada la pública, no afecta
la evidencia pasada; para seguir firmando, runbook de Vault persistente en prod
(Raft + auto-unseal + snapshots) + re-provisión idempotente (`vault-init`).

---

## Plan de ejecución (orden de menor a mayor riesgo)

| Tarea | Hallazgo | Migración | Estado |
|---|---|---|---|
| F8-1 | tabla `signing_keys` + col en `chain_anchors` | sí (0013) | ✅ |
| F8-2 | archivar pública en write-time (best-effort, idempotente) | no | ✅ |
| F8-3 | export/anchor sirven pública durable-first | no | ✅ |
| F8-4 | verificador offline standalone | no | ✅ |
| F8-5 | docs ADR-015 + ROADMAP F8 + runbook Vault prod | no | ✅ |

Cada tarea se verifica con `pytest` (suite API, baseline 273) antes de marcarse ✅.

---

## Consecuencias

**Positivas:**
- La evidencia es **auto-contenida**: verificable offline, por cualquiera, para
  siempre, sin Vault y sin confiar en SafeContext.
- Sobrevive a rotación de clave y a la pérdida/decomiso del KMS.
- Habilita el "paquete de evidencia portátil" para auditoría/tribunal y el futuro
  modo sidecar.

**Negativas / Trade-offs:**
- Una llamada extra a Vault por *versión* de clave (no por operación: se cachea en
  `signing_keys`).
- La pública se almacena en BD (no es secreto — la privada nunca sale de Vault).
- La durabilidad de Vault en prod sigue siendo necesaria para *seguir firmando* y
  rotar (no para verificar lo ya firmado).

---

## Alternativas consideradas

| Alternativa | Razón de descarte |
|---|---|
| Sólo endurecer Vault dev (file storage + auto-unseal) | Comodidad de dev; no hace la evidencia auto-contenida (sigue dependiendo de Vault para verificar) |
| Fetch en vivo de la pública en cada verificación | Acopla la verificación a Vault vivo y a la versión actual de la clave |
| Anclar la pública en una blockchain externa | Sobre-ingeniería; archivar PEM + firma asimétrica es suficiente |

---

## Referencias

- `apps/api/db/models/signing_key.py` — archivo durable de claves públicas
- `apps/api/db/evidence.py` — `get_transit_public_key`, `archive_public_key_if_needed`
- `apps/api/api/v1/audit.py` — `_resolve_public_key`, export y anchor
- `apps/tools/verify_offline.py` — verificador offline
- `apps/docs/runbooks/vault-kms-durability.md` — durabilidad de Vault en prod
- ADR-014 (no-repudio write-time), ADR-008 (MinIO WORM)
