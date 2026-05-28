# Manual 09 · Seguridad y Compliance

**Versión**: 1.0.0 · **Estado**: Activo · **Fecha**: 2026-05-25
**Audiencia**: CISO, equipo de seguridad, auditores, compliance officers, arquitectos
**Fuente de verdad**: Código en `core/`, `policies/`, `.github/workflows/ci.yml`, configuración Docker Compose
**Documentos relacionados**: [DOC-PRODUCTO.md](../DOC-PRODUCTO.md) §7, [Manual 08 — Roles](./08_ROLES_Y_PERMISOS.md), [Manual 01 — Arquitectura](./01_ARQUITECTURA_TECNICA.md)

---

## Tabla de contenidos

1. [Modelo de seguridad](#1-modelo-de-seguridad)
2. [Autenticación y autorización](#2-autenticación-y-autorización)
3. [Cifrado y protección de datos](#3-cifrado-y-protección-de-datos)
4. [Cadena de custodia criptográfica](#4-cadena-de-custodia-criptográfica)
5. [Compliance frameworks](#5-compliance-frameworks)
6. [Auditoría](#6-auditoría)
7. [DevSecOps](#7-devsecops)
8. [Operación air-gapped](#8-operación-air-gapped)
9. [Multi-tenancy y aislamiento](#9-multi-tenancy-y-aislamiento)

---

## 1. Modelo de seguridad

SafeContext implementa **defensa en profundidad** con 7 capas de protección. Cada capa opera independientemente — el compromiso de una no invalida las demás.

### 1.1. Capas de seguridad

```
┌─────────────────────────────────────────────────────┐
│ Capa 7: Auditoría inmutable                         │
│   pgAudit + chain_hash + WORM + SIEM               │
├─────────────────────────────────────────────────────┤
│ Capa 6: Cifrado                                     │
│   TLS en tránsito, SSE en reposo, Transit signing   │
├─────────────────────────────────────────────────────┤
│ Capa 5: Aislamiento de datos                        │
│   RLS PostgreSQL por tenant, MinIO por tenant       │
├─────────────────────────────────────────────────────┤
│ Capa 4: Control de acceso                           │
│   RBAC (4 roles), SoD, OPA por tenant              │
├─────────────────────────────────────────────────────┤
│ Capa 3: Autenticación                               │
│   Keycloak OIDC + MFA, OAuth 2.1 + PKCE (MCP)     │
├─────────────────────────────────────────────────────┤
│ Capa 2: Red                                         │
│   nginx reverse proxy, 3 redes Docker aisladas     │
├─────────────────────────────────────────────────────┤
│ Capa 1: Supply chain                                │
│   SBOM, cosign, SLSA provenance, detect-secrets    │
└─────────────────────────────────────────────────────┘
```

### 1.2. Principios

| Principio | Implementación |
|---|---|
| Zero-trust | Cada request valida JWT + MFA; no hay sesiones implícitas entre servicios |
| Mínimo privilegio | 4 roles sin herencia; cada endpoint declara roles explícitamente |
| Inmutabilidad de registros | chain_hash + WORM + firma digital; no hay operación de UPDATE en audit trail |
| Fail-secure | Si OPA, TSA o Vault no están disponibles, la operación falla (no pasa sin verificar) |
| Separación de funciones | SoD enforced: quien escanea no puede aprobar sus propios hallazgos |

---

## 2. Autenticación y autorización

### 2.1. Keycloak OIDC (UI y API REST)

| Aspecto | Configuración |
|---|---|
| Protocolo | OpenID Connect 1.0 |
| Realm | `safecontext` |
| Cliente UI | `safecontext-ui` (public, PKCE) |
| Audience | `safecontext-api` (audience mapper en access token) |
| Algoritmo JWT | RS256 (clave asimétrica, JWKS auto-rotado) |
| MFA | OTP requerido en producción (`amr` claim contiene `otp`) |
| Sesión UI | Cookie httpOnly `sc_session`, 8 horas, sin JavaScript access |

**Referencia**: `core/auth_oidc.py` — validación JWT con PyJWT, JWKS cache 15 min TTL, double-checked locking.

### 2.2. OAuth 2.1 + PKCE (MCP)

| Aspecto | Configuración |
|---|---|
| Protocolo | OAuth 2.1 (draft-ietf-oauth-v2-1) |
| Flow | Authorization Code + PKCE (S256) |
| Scopes | `mcp:scan`, `mcp:sanitize`, `mcp:classify`, `mcp:audit`, `mcp:policy`, `mcp:approve` |
| Consentimiento | Explícito por scope, UI de consentimiento de Keycloak |
| Token validation | `mcp/auth.py:require_mcp_oauth` |

**Referencia**: `mcp/auth.py`, `mcp/scopes.py` — scope enforcement per-tool.

### 2.3. Rate limiting

Dos niveles de protección contra abuso:

| Nivel | Scope | Almacenamiento | Configuración |
|---|---|---|---|
| MCP client | Por `client_id` | Redis sorted sets (multi-instancia) o in-memory (fallback) | `MCP_RATE_LIMIT_RPM` en settings |
| Tenant | Por `tenant_id` | Redis o in-memory | `rate_limit_rpm` en tabla `tenants` |
| Diario | Por `tenant_id` | Redis con TTL diario o in-memory | `max_scans_per_day` en tabla `tenants` |
| Tamaño | Por request | Validación síncrona | `max_document_size` en tabla `tenants` |

**Referencia**: `core/auth_oidc.py:check_rate_limit_redis`, `core/quotas.py`.

### 2.4. Headers de seguridad (nginx)

El proxy reverso nginx inyecta headers en todas las respuestas:

| Header | Valor | Propósito |
|---|---|---|
| `X-Frame-Options` | `DENY` | Prevención de clickjacking |
| `X-Content-Type-Options` | `nosniff` | Prevención de MIME sniffing |
| `X-XSS-Protection` | `1; mode=block` | Protección XSS legacy |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control de referrer |

---

## 3. Cifrado y protección de datos

### 3.1. En tránsito

| Conexión | Protocolo | Configuración |
|---|---|---|
| Cliente → nginx | TLS 1.2/1.3 | Certificado configurable; self-signed en dev |
| nginx → API | HTTP (red interna Docker) | Red aislada `sc-frontend` |
| API → PostgreSQL | SSL | `sslmode=require` en connection string |
| API → Redis | Sin TLS en dev | TLS configurable para producción |
| API → MinIO | HTTP/HTTPS | `MINIO_USE_SSL` configurable |
| API → OpenBao | HTTP en dev | HTTPS recomendado en producción |

### 3.2. En reposo

| Dato | Protección | Detalle |
|---|---|---|
| Artefactos MinIO | SSE (Server-Side Encryption) | MinIO encrypta automáticamente con clave maestra |
| Base de datos | Cifrado de volumen | Depende del storage driver del host |
| Evidencia WORM | SSE + Object Lock GOVERNANCE | Inmutable por 7 años (2555 días por defecto) |
| Certificados borrado | SSE + Object Lock | Misma retención que evidencia |

### 3.3. KMS — OpenBao Transit

SafeContext usa OpenBao (fork open-source de Vault) para gestión de claves criptográficas.

| Aspecto | Configuración |
|---|---|
| Engine | Transit (firma digital, no cifrado de datos) |
| Algoritmo | ECDSA-P256 |
| Clave | `safecontext-signing` (exportable para verificación offline) |
| Rotación | Soportada por Transit (versionado de claves) |
| Operaciones | `sign_data()`, `verify_signature()`, `get_public_key()` |

**Referencia**: `core/vault_transit.py` — cliente async con timeout 5s, fallback graceful.

**Cómo verificar una firma offline:**
1. Exportar la clave pública: `GET /v1/transit/keys/safecontext-signing`
2. Extraer el PEM del campo `public_key`
3. Verificar con OpenSSL: `openssl dgst -sha256 -verify pubkey.pem -signature sig.bin data.json`

---

## 4. Cadena de custodia criptográfica

SafeContext mantiene una cadena de custodia verificable para cada operación de escaneo. Esto garantiza que las evidencias de auditoría no pueden ser manipuladas sin detección.

### 4.1. chain_hash — Hash encadenado

Cada operación completada recibe un hash encadenado:

```
chain_hash = SHA256(prev_chain_hash || operation_hash)
operation_hash = SHA256(JSON(id, trace_id, actor_id, artifact_digest, status, created_at))
```

| Propiedad | Efecto |
|---|---|
| Detección de manipulación | Si se modifica un registro, el chain_hash no coincide |
| Detección de eliminación | Un gap en la cadena indica registros borrados |
| Prueba de orden | La cadena demuestra la secuencia temporal |
| Per-tenant | Cada tenant tiene su cadena independiente |
| Genesis hash | `0x0000...` (64 ceros) para el primer registro |

**Verificación programática**: `core/chain.py:verify_chain(db, tenant_id)` — retorna `{valid, checked, first_broken_at, gaps}`.

### 4.2. Firma digital Transit

Las evidencias de auditoría se firman digitalmente con la clave ECDSA-P256 de OpenBao Transit:

1. El endpoint `GET /v1/audit/{trace_id}` serializa la evidencia completa
2. `core/vault_transit.py:sign_data()` firma los bytes con Transit
3. La respuesta incluye `digital_signature` (base64) y `signing_key_version`
4. La clave pública es exportable para verificación independiente

### 4.3. TSA — Sellado temporal RFC 3161

Para no-repudiación temporal, las evidencias reciben un sello de tiempo de una autoridad externa (TSA):

| Aspecto | Detalle |
|---|---|
| Estándar | RFC 3161 (Time-Stamp Protocol) |
| TSA dev | FreeTSA (`freetsa.org/tsr`) |
| TSA prod | Configurable (`settings.tsa_url`) — CA interna o comercial |
| Hash | SHA-256 del documento |
| Timeout | 10 segundos, fallback graceful |
| Certificado | Incluido en respuesta (campo `certReq: TRUE`) |

**Referencia**: `core/tsa.py` — construye TimeStampReq ASN.1 DER manual, verifica presencia de digest.

**Verificación offline del sello TSA:**
```bash
openssl ts -verify -in token.tsr -data original.json -CAfile tsa_ca.pem
```

### 4.4. WORM — Retención inmutable

Las evidencias de auditoría y certificados de borrado se almacenan en MinIO con Object Lock:

| Aspecto | Configuración |
|---|---|
| Modo | GOVERNANCE (permite bypass con permiso especial `s3:BypassGovernanceRetention`) |
| Retención | 2555 días (7 años) por defecto |
| Bucket | `safecontext-audit-evidence` (Object Lock habilitado en creación) |
| Bypass | Solo en emergencia, función `delete_with_governance_bypass()`, requiere log de advertencia |

**Referencia**: `core/worm.py` — `store_with_retention()`, `check_retention()`, `delete_with_governance_bypass()`.

### 4.5. Evidencia completa de una operación

Una operación completada genera la siguiente cadena de evidencia:

```
Operación (PostgreSQL)
  ├── trace_id (UUID v4, correlación end-to-end)
  ├── artifact_digest (SHA-256 del documento original)
  ├── chain_hash (hash encadenado, verificable)
  ├── policy_version (versión de OPA usada)
  ├── actor_id (UUID del JWT, atribución real)
  │
  ├── Hallazgos (N findings)
  │   └── detector, rule_id, confidence, severity, spans
  │
  ├── Redacciones (N redactions, si aprobadas)
  │   └── approved_by, approval_trace_id, policy_version
  │
  ├── Firma digital (ECDSA-P256 via OpenBao Transit)
  ├── Sello temporal (TSA RFC 3161)
  ├── HMAC-SHA256 (verificación de integridad)
  │
  └── WORM (MinIO Object Lock, 7 años)
```

---

## 5. Compliance frameworks

### 5.1. GDPR (Reglamento General de Protección de Datos)

| Artículo | Requisito | Implementación SafeContext |
|---|---|---|
| Art. 5(1)(e) | Limitación del plazo de conservación | `retention_days` configurable por tenant (default 365 días) |
| Art. 5(2) | Principio de responsabilidad | Certificados de borrado firmados, audit trail inmutable |
| Art. 17 | Derecho de supresión | `run_gdpr_purge()` con certificado HMAC-SHA256 |
| Art. 25 | Protección de datos por diseño | Detección y sanitización automática de PII |
| Art. 30 | Registro de actividades | Audit trail con trace_id, actor_id, policy_version |
| Art. 32 | Seguridad del tratamiento | Cifrado en tránsito/reposo, RBAC, MFA, RLS |

**Flujo de purga GDPR:**

1. Admin ejecuta `POST /v1/admin/tenants/{id}/purge` o el scheduler automático
2. `find_expired_operations()` localiza operaciones anteriores al `cutoff`
3. Se cuentan registros hijos (findings, redactions, artifacts)
4. `DELETE` con CASCADE en PostgreSQL
5. `generate_deletion_certificate()` crea certificado firmado HMAC-SHA256
6. `store_deletion_certificate()` almacena en WORM (7 años)
7. Se retorna resumen con `certificate_id`

**Referencia**: `core/retention_gdpr.py` — `DeletionCertificate`, `run_gdpr_purge()`.

### 5.2. SOC 2 (Trust Service Criteria)

| Criterio | Categoría | Control SafeContext |
|---|---|---|
| CC6.1 | Acceso lógico | Keycloak OIDC + MFA, 4 roles RBAC |
| CC6.3 | Acceso basado en roles | `require_admin`, `require_reviewer`, `_require_privileged` |
| CC6.6 | Segregación de funciones | `check_self_approval()` — SoD enforced |
| CC7.2 | Monitoreo de actividad | pgAudit, SIEM (CEF/LEEF/JSON), audit trail |
| CC7.3 | Detección de incidentes | Escaneo automático de PII, alertas SIEM |
| CC8.1 | Gestión de cambios | CI/CD con gates de seguridad, SBOM firmado |
| A1.2 | Recuperación | Backups PostgreSQL, MinIO replicable, DR drill |
| PI1.1 | Integridad de datos | chain_hash, firma digital, TSA, HMAC |

### 5.3. ISO 27001 (Controles Annex A)

| Control | Descripción | Implementación |
|---|---|---|
| A.5.15 | Control de acceso | RBAC 4 roles + SoD |
| A.5.23 | Seguridad de la información para servicios cloud | Multi-tenancy con RLS, aislamiento por tenant |
| A.8.3 | Restricción de acceso a la información | OPA policies per-tenant, waivers con justificación |
| A.8.5 | Autenticación segura | OIDC + MFA + PKCE |
| A.8.9 | Gestión de configuración | Settings centralizados, ADRs inmutables |
| A.8.24 | Uso de criptografía | ECDSA-P256 (firma), SHA-256 (hashing), HMAC-SHA256 (integridad) |
| A.8.25 | Ciclo de vida de desarrollo seguro | CI con detect-secrets, lint, OPA tests, recall gate |

### 5.4. Reportes de compliance

SafeContext genera verificaciones automatizadas en el pipeline CI:

| Check | Herramienta | Gate |
|---|---|---|
| Secretos en código | `detect-secrets` | Falla si hay secretos no permitidos |
| Políticas OPA | `opa test` con coverage | ≥ 80% coverage requerido |
| Recall de detección | `test_recall.py` | Umbrales mínimos por tipo de entidad |
| Dependencias Python | `pip-audit` (recomendado) | Verificar vulnerabilidades conocidas |
| Dependencias Node | `npm audit` (recomendado) | Verificar vulnerabilidades conocidas |

---

## 6. Auditoría

### 6.1. pgAudit (PostgreSQL)

pgAudit registra todas las operaciones SQL a nivel de base de datos, independiente de la aplicación.

| Configuración | Valor |
|---|---|
| `pgaudit.log` | `write, ddl` (registra INSERT, UPDATE, DELETE, y cambios de schema) |
| `pgaudit.log_catalog` | `off` (no registrar queries al catálogo del sistema) |
| Almacenamiento | Logs de PostgreSQL, recopilables por Loki/Grafana |

### 6.2. Audit trail de aplicación

Cada operación de escaneo genera un registro de auditoría completo:

| Campo | Fuente | Propósito |
|---|---|---|
| `trace_id` | UUID v4 generado por OpenTelemetry | Correlación end-to-end |
| `artifact_digest` | SHA-256 del documento | Verificar que el documento no cambió |
| `actor_id` | `sub` claim del JWT Keycloak | Atribución a usuario real |
| `actor_type` | `human` o `mcp_agent` | Distinguir acceso humano de agente |
| `policy_version` | OPA query | Qué versión de política se aplicó |
| `chain_hash` | SHA-256 encadenado | Integridad de la cadena |
| `digital_signature` | ECDSA-P256 via Transit | No-repudiación |
| `tsa_token` | RFC 3161 | Prueba temporal independiente |
| `hmac` | HMAC-SHA256 con `api_secret_key` | Integridad verificable |

### 6.3. Exportación SARIF

Las evidencias se pueden exportar en formato SARIF (Static Analysis Results Interchange Format) para integración con GitHub Advanced Security:

```
GET /v1/audit/{trace_id}/sarif
```

El formato SARIF incluye: tool metadata, reglas aplicadas, resultados con ubicaciones, severidades y mensajes.

### 6.4. SIEM — Integración con plataformas de seguridad

SafeContext emite eventos de seguridad a plataformas SIEM configuradas por tenant:

| Formato | Estándar | Plataformas principales |
|---|---|---|
| CEF | Common Event Format | Splunk, ArcSight, QRadar |
| LEEF | Log Event Extended Format | IBM QRadar |
| JSON | Estructurado | Elasticsearch, Datadog, cualquier SIEM moderno |

**Transporte:**

| Método | Protocolo | Configuración |
|---|---|---|
| Webhook | HTTPS POST | `webhook_url`, `webhook_token` (Bearer) |
| Syslog UDP | RFC 5424 | `syslog_host`, `syslog_port` (default 514) |
| Syslog TCP | RFC 5424 | `syslog_host`, `syslog_port`, `syslog_protocol: tcp` |

**Eventos emitidos:**

| Evento | Severidad CEF | Cuándo |
|---|---|---|
| `scan.completed` | 1 (info) | Escaneo completado |
| `finding.detected` | 2-10 (según severidad) | Hallazgo de dato sensible |
| `review.approved` | 1 (info) | Hallazgo aprobado por reviewer |
| `review.rejected` | 1 (info) | Hallazgo rechazado |
| `retention.purge` | 4 (warning) | Purga GDPR ejecutada |
| `siem.test` | 1 (info) | Prueba de conectividad |

**Comportamiento**: fire-and-forget con timeout de 5s para webhook, 3s para syslog. Las fallas se registran en log pero nunca bloquean la operación principal.

**Referencia**: `core/siem.py` — `SIEMConfig`, `SIEMEvent`, `emit_siem_event()`, constructores de conveniencia.

---

## 7. DevSecOps

### 7.1. Pipeline CI — Gates de seguridad

El pipeline CI (`.github/workflows/ci.yml`) ejecuta los siguientes gates de seguridad en cada push y PR:

| Job | Qué verifica | Falla si |
|---|---|---|
| `detect-secrets` | Secretos hardcoded en código | Hay secretos nuevos fuera del baseline |
| `lint-python` | Calidad y estilo de código (ruff) | Errores de lint o formato |
| `test-api` | Tests de API (Python 3.12 + 3.14) | Cualquier test falla |
| `test-ui` | Tests frontend (Jest) | Cualquier test falla |
| `test-opa` | Tests de políticas OPA | Coverage < 80% o tests fallan |
| `test-recall` | Recall del detector ML | Por debajo de umbrales mínimos |
| `safecontext-gate` | Auto-escaneo de SafeContext | Hallazgo critical en el propio código |
| `test-e2e` | Playwright E2E (solo main) | Cualquier flujo de usuario falla |

### 7.2. Supply chain

| Control | Herramienta | Propósito |
|---|---|---|
| SBOM | CycloneDX | Bill of Materials de dependencias |
| Firma de imágenes | cosign (Sigstore) | Verificar origen de contenedores |
| SLSA provenance | GitHub Actions attestation | Trazabilidad de build |
| Secret scanning | detect-secrets | Prevenir secretos en repo |
| Dependency audit | pip-audit, npm audit | Vulnerabilidades conocidas |

### 7.3. Pentesting automatizado (recomendado)

| Herramienta | Tipo | Integración |
|---|---|---|
| ZAP (OWASP) | DAST — baseline scan | CI job contra staging |
| Nuclei | Scanner de vulnerabilidades | CI job con templates actualizados |

---

## 8. Operación air-gapped

SafeContext puede operar completamente desconectado de Internet para entornos clasificados o regulados.

### 8.1. Sin dependencias externas

| Componente | Alternativa offline |
|---|---|
| PyPI/npm | Registry interno (Harbor, Verdaccio) |
| Docker Hub | Harbor como mirror/registry privado |
| TSA (FreeTSA) | TSA interna con CA propia |
| Keycloak themes | Incluidos en imagen |
| spaCy model | `en_core_web_lg` embebido en imagen |
| OPA bundles | Incluidos en volumen Docker |

### 8.2. Bundle de actualización offline

Para actualizar un entorno air-gapped:

1. En entorno conectado: `docker save` de todas las imágenes + tarball de código
2. Transferir via medio físico aprobado
3. En entorno air-gapped: `docker load` + `docker compose up`
4. Las migraciones Alembic se ejecutan automáticamente al arrancar

### 8.3. DR drill sin Internet

El plan de recuperación ante desastres funciona sin conectividad:
- PostgreSQL: backup/restore via `pg_dump`/`pg_restore` desde volumen local
- MinIO: replicación site-to-site configurable
- Keycloak: export/import de realm via CLI
- Configuración: `docker-compose.yml` + `.env` son la fuente de verdad

---

## 9. Multi-tenancy y aislamiento

### 9.1. Row-Level Security (RLS) — PostgreSQL

Cada tabla con datos de tenant tiene RLS habilitado:

| Tabla | Columna de tenant | Política |
|---|---|---|
| `operations` | `tenant_id` | `USING (tenant_id = current_setting('app.tenant_id')::uuid)` |
| `findings` | via `operations.tenant_id` | CASCADE join |
| `redactions` | via `operations.tenant_id` | CASCADE join |
| `waivers` | `tenant_id` | `USING (tenant_id = current_setting('app.tenant_id')::uuid)` |

**Migración**: `0009_rls.py` — habilita RLS y crea políticas.

### 9.2. Aislamiento en OPA

Cada tenant puede tener su propia configuración de políticas:

| Personalización | Campo en `tenant_config` | Efecto |
|---|---|---|
| Umbrales de confianza | `confidence_overrides` | Ajustar sensibilidad por tipo de entidad |
| Severidades | `severity_overrides` | Cambiar nivel base de severidad |
| Tipos bloqueados | `blocked_entity_types` | Bloquear siempre ciertos tipos (ej: SSN) |

**Referencia**: `policies/base/safecontext.rego:tenant_decision()`.

### 9.3. Aislamiento en MinIO

Los artefactos se almacenan bajo path del tenant:
```
safecontext-audit-evidence/
  └── {tenant_id}/
      ├── {trace_id}/audit.json
      └── deletion-certificates/{cert_id}.json
```

### 9.4. Quotas por tenant

Cada tenant tiene límites configurables:

| Quota | Campo en `tenants` | Enforcement |
|---|---|---|
| Escaneos diarios | `max_scans_per_day` | Redis counter con TTL 25h + fallback in-memory |
| Tamaño documento | `max_document_size` | Validación síncrona en bytes UTF-8 |
| Requests por minuto | `rate_limit_rpm` | Sliding window in-memory |
| Almacenamiento | `max_storage_mb` | Verificación en MinIO (futuro) |

**Referencia**: `core/quotas.py` — `check_daily_scan_quota()`, `check_document_size()`, `check_tenant_rate_limit()`.

### 9.5. Redes Docker

La infraestructura Docker utiliza 3 redes aisladas:

| Red | Servicios | Propósito |
|---|---|---|
| `sc-frontend` | nginx, UI, API | Tráfico HTTP entre frontend y backend |
| `sc-backend` | API, PostgreSQL, Redis, MinIO, OPA, workers | Tráfico interno de datos |
| `sc-monitoring` | Grafana, Loki, Tempo, Prometheus | Observabilidad aislada |

Los servicios solo tienen acceso a las redes que necesitan. PostgreSQL no está expuesto a la red frontend.

---

## Resumen de módulos de seguridad por archivo

| Módulo | Archivo | Responsabilidad |
|---|---|---|
| Autenticación OIDC | `core/auth_oidc.py` | JWT validation, MFA, RBAC, rate limiting, SoD |
| OAuth MCP | `mcp/auth.py` | OAuth 2.1 + PKCE para agentes MCP |
| Scopes MCP | `mcp/scopes.py` | Enforcement de scopes por tool |
| Chain hash | `core/chain.py` | Hash encadenado per-tenant para audit trail |
| Firma digital | `core/vault_transit.py` | ECDSA-P256 via OpenBao Transit |
| Sellado temporal | `core/tsa.py` | RFC 3161 TSA client |
| WORM storage | `core/worm.py` | MinIO Object Lock GOVERNANCE |
| Retención GDPR | `core/retention_gdpr.py` | Purga con certificados firmados |
| SIEM | `core/siem.py` | CEF/LEEF/JSON a webhook y syslog |
| Quotas | `core/quotas.py` | Rate limiting y quotas por tenant |
| Políticas OPA | `policies/base/safecontext.rego` | Evaluación de detección, waivers, tenant config |

---

*Última actualización: 2026-05-25 · Versión 1.0.0*
