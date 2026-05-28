# ADR-014 · Endurecimiento del no-repudio del audit trail

**Estado**: Aceptado (ejecutado — F7-1..F7-6 completados 2026-05-28)
**Fecha**: 2026-05-28
**Contexto**: Evidencias firmadas con validez legal (F6-B) — revisión de no-repudio
**Relacionado**: ADR-001 (PostgreSQL registro), ADR-008 (MinIO WORM), F6-B1/B2/B3/B4

---

## Contexto

F6-B construyó cuatro mecanismos de evidencia sobre el audit export
(`GET /v1/audit/{trace_id}`):

1. **HMAC-SHA256** (`core` en `api/v1/audit.py`) — integridad con secreto compartido.
2. **Hash chain** (`core/chain.py`) — anti-tampering + orden + detección de borrado.
3. **TSA RFC 3161** (`core/tsa.py`) — prueba de existencia en el tiempo.
4. **Firma asimétrica ECDSA-P256** (`core/vault_transit.py`) — no-repudio, clave
   pública exportable para verificación offline.

La capa criptográfica es sólida y los primitivos correctos están presentes. Sin
embargo, una revisión de seguridad (sesión 2026-05-28) detectó que **la disciplina
de aplicación** de esos primitivos deja seis huecos que, juntos, impiden que el
audit trail sirva como prueba de no-repudio frente a un insider con acceso a la BD
o frente a un tribunal/auditor que cuestione la cadena de custodia.

El hallazgo más grave: **`compute_and_set_chain_hash()` no tiene ningún llamador
en el código** — `audit.py` solo *lee* `operation.chain_hash`, nunca lo computa.
El chain_hash nunca se está poblando en el flujo real, por lo que la cadena de
custodia hoy es inexistente en la práctica, no solo débil.

---

## Decisión

Mover la disciplina criptográfica de **read-time a write-time**, hacer la firma
asimétrica **obligatoria y bloqueante** (configurable, fail-closed en producción),
y **sellar la cabeza de la cadena** para que sea tamper-proof y no solo
tamper-evident. El HMAC se degrada a checksum auxiliar (se mantiene por
compatibilidad, deja de ser la firma de autoridad).

Estos cambios convierten cada operación completada en un **registro
auto-probatorio** (firmado en el momento del evento, encadenado y verificable sin
confiar en SafeContext), que es además el prerrequisito técnico para el modo
sidecar/proxy portátil (ver nota de arquitectura del backlog F7).

---

## Hallazgos y estado

Leyenda de estado: `🔲 PENDIENTE` · `🔄 EN CURSO` · `✅ COMPLETADO`

### H1 · Se firma al LEER, no al OCURRIR — 🔴 crítico — ✅ COMPLETADO (2026-05-28)

`get_audit_export` calcula HMAC y firma Vault en el momento del `GET`, con
`exported_at = datetime.now()` (hora de lectura). Se firma "una vista de la BD al
exportar", no "el evento tal como ocurrió". Si la fila se altera entre el evento y
el export, la firma certifica la versión alterada.

**Fix**: firmar el `operation_hash` canónico en write-time (al completarse la
operación) y persistir la firma + `signed_at` + versión de clave en la fila.

### H2 · Firma fuerte opcional; HMAC obligatorio (prioridades invertidas) — 🔴 crítico — ✅ COMPLETADO (2026-05-28)

`sign_data` está en try/except: si Vault no responde, `digital_signature=None` y el
export sigue. Lo único garantizado es el HMAC con `api_secret_key` (secreto del
propio servidor) — inútil como prueba *contra* SafeContext.

**Fix**: nuevo setting `audit_require_digital_signature` (default `False` para no
romper dev/tests; `True` obligatorio en producción). Cuando es `True` y la firma
asimétrica falla → 503, no se emite export sin firma. HMAC documentado como
checksum auxiliar.

### H3 · Cadena tamper-EVIDENT, no tamper-PROOF (y sin poblar) — 🔴 crítico — ✅ COMPLETADO (2026-05-28)

`chain.py` usa SHA256 puro sin secreto ni firma; un insider con escritura recomputa
toda la cadena posterior y `verify_chain` da `valid: true`. Además
`compute_and_set_chain_hash` **no se llama desde ningún punto** → chain_hash nunca
se puebla.

**Fix**: (a) wirear el sellado de cadena en write-time al completarse la operación;
(b) firmar la cabeza de la cadena con la clave asimétrica (y opcionalmente TSA),
persistida en tabla `chain_anchors`, vía `POST /v1/audit/chain/anchor`.

### H4 · Clave de firma `exportable: True` — 🟡 alto — ✅ COMPLETADO (2026-05-28)

`_ensure_transit_key` crea la clave Transit con `"exportable": True`, lo que permite
extraer la **clave privada** de Vault. Para no-repudio la clave debe ser
no-exportable (sign-only). La clave pública se obtiene del endpoint `keys` sin
necesidad de `exportable`.

**Fix**: `"exportable": False`. Documentar que claves ya creadas como exportables
deben rotarse a una nueva no-exportable.

### H5 · `verify_signature` hardcodea `vault:v1:` — 🟡 alto — ✅ COMPLETADO (2026-05-28)

`verify_signature` antepone `vault:v1:` fijo; no verifica firmas hechas con
versiones rotadas de la clave (v2+). Al rotar, la verificación de evidencia
histórica se rompe.

**Fix**: preservar/parsea la versión real de la firma; soportar versiones
históricas.

### H6 · Mismatch de algoritmo de firma — ⚪ menor — ✅ COMPLETADO (2026-05-28)

El payload de `sign_data` envía `"signature_algorithm": "pkcs1v15"` (esquema RSA)
sobre una clave `ecdsa-p256`. Vault lo ignora para ECDSA, pero delata que el esquema
no se eligió con cuidado.

**Fix**: omitir `signature_algorithm` para claves ECDSA (o condicionarlo al tipo de
clave).

---

## Plan de ejecución (orden de menor a mayor riesgo)

| Tarea | Hallazgo | Migración | Endpoint | Estado |
|---|---|---|---|---|
| F7-1 | H6 — fix algoritmo ECDSA | no | no | ✅ |
| F7-2 | H5 — versión de clave en verify | no | no | ✅ |
| F7-3 | H4 — clave no-exportable | no | no | ✅ |
| F7-4 | H2 — firma asimétrica obligatoria (gated) | no | no | ✅ |
| F7-5 | H1 — sellado/firma en write-time | sí (0012) | no | ✅ |
| F7-6 | H3 — anclaje de cabeza de cadena | sí (0012) | sí (`/audit/chain/anchor`) | ✅ |

Cada tarea se verifica con `pytest` (suite de evidencia + audit, baseline 38/38) y
se marca `✅ COMPLETADO` aquí y en `ROADMAP.md §F7` solo tras pasar los tests.

---

## Consecuencias

**Positivas:**
- El audit trail pasa de "tamper-evident parcial" a no-repudio real verificable por
  un tercero sin confiar en SafeContext.
- Habilita el registro de evidencia portátil (write-time, append-only firmado) que
  necesita el futuro modo sidecar/proxy MCP.
- Cierra el hueco crítico de que la cadena de custodia no se estaba poblando.

**Negativas / Trade-offs:**
- Firmar en write-time agrega una llamada a Vault en el path de completar la
  operación (mitigable: async/fire-and-forget para el anclaje, bloqueante solo para
  la firma de la operación).
- `audit_require_digital_signature=True` hace que el export dependa de Vault
  disponible — correcto para producción, configurable para air-gapped.
- Las claves Transit ya creadas como exportables requieren rotación manual.

---

## Alternativas consideradas

| Alternativa | Razón de descarte |
|---|---|
| Mantener firma solo en read-time | No prueba el evento, solo una vista posterior de la BD |
| Firmar con HMAC reforzado (clave en KMS) | HMAC sigue siendo simétrico: firmante = verificador, no hay no-repudio |
| Anclar cada operación a un ledger externo (blockchain) | Sobre-ingeniería para el caso; TSA + firma de cabeza de cadena es suficiente |
| Hacer la firma asimétrica siempre bloqueante | Rompe dev/tests/air-gapped sin Vault; se prefiere gating por setting |

---

## Referencias

- `apps/api/api/v1/audit.py` — export, HMAC, ensamblaje de evidencia
- `apps/api/core/chain.py` — hash chain (sin llamadores actualmente)
- `apps/api/core/vault_transit.py` — firma ECDSA-P256, clave exportable
- `apps/api/core/tsa.py` — RFC 3161
- `apps/docs/ROADMAP.md §F7` — backlog con las tareas F7-1..F7-6
- ADR-001 (PostgreSQL registro inmutable), ADR-008 (MinIO WORM)
