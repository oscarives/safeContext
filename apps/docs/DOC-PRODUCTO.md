# SafeContext — Documento de Producto
**Version**: 1.0.0 | **Estado**: Activo | **Fecha**: 2026-05-25
**Autoridad**: Este documento es la fuente de verdad del producto. Ante contradiccion con cualquier otro documento, este prevalece.
**Audiencia**: Stakeholders, Product Owner, Arquitecto, Tech Lead, Compliance, Agentes Claude Code
**Reemplaza**: DOC-0_UNIFIED.md, DOC-1_PRD.md, DOC-2_SAD.md, DOC-3_SPEC.md (archivados en `docs/archive/`)

> **Estado del proyecto (2026-05-25)**: Madurez 5/5. F1-F6 completadas. T1-T10 completados. Admin Module completado. 112 UI tests + 233+ backend tests. Docker testing 59/59 pass.
> Para estado detallado de implementacion ver `docs/ROADMAP.md`.

---

## Tabla de contenidos

1. [Vision y proposito](#1-vision-y-proposito)
2. [Problema que resuelve](#2-problema-que-resuelve)
3. [Usuarios y audiencias](#3-usuarios-y-audiencias)
4. [Modelo funcional](#4-modelo-funcional)
5. [Requisitos funcionales](#5-requisitos-funcionales)
6. [Requisitos no funcionales](#6-requisitos-no-funcionales)
7. [Arquitectura](#7-arquitectura)
8. [Modelo de datos](#8-modelo-de-datos)
9. [Decisiones de arquitectura (ADRs)](#9-decisiones-de-arquitectura-adrs)
10. [Stack tecnologico](#10-stack-tecnologico)
11. [Principios no negociables](#11-principios-no-negociables)
12. [Fases y criterios de aceptacion](#12-fases-y-criterios-de-aceptacion)
13. [Modelo de madurez](#13-modelo-de-madurez)
14. [Fuera de alcance](#14-fuera-de-alcance)

---

## 1. Vision y proposito

SafeContext es una plataforma Enterprise-grade de sanitizacion, clasificacion y gobierno de documentos y datos sensibles, disenada para ser consumida tanto por humanos como por agentes de inteligencia artificial.

**Proposito central**: garantizar que ningun documento sensible llegue a un modelo de IA, pipeline de CI/CD o sistema externo sin haber pasado por un proceso verificable, auditable y explicable de deteccion, sanitizacion y aprobacion.

**Diferencial competitivo**:
- No es un escaner de secretos. Es un sistema de gobierno de contexto para entornos donde la IA consume documentos.
- Expone sus capacidades como **MCP Server**, permitiendo que cualquier agente LLM compatible (Claude, Codex, GitHub Copilot, etc.) consuma SafeContext como herramienta nativa, sin lock-in de interfaz.
- Opera con agentes internos especializados que corren localmente, garantizando compatibilidad con entornos air-gapped y despliegues regulados.
- Toda decision es explicable, auditable e inmutable.
- **Multi-tenant nativo**: aislamiento de datos por tenant con RLS, politicas OPA por tenant y quotas configurables.
- **Evidencias con validez legal**: cadena de custodia criptografica (chain hash), firma digital (OpenBao Transit), sellado temporal (TSA RFC 3161) y retencion WORM.

---

## 2. Problema que resuelve

| Problema | Consecuencia sin SafeContext |
|---|---|
| Documentos con PII, secretos o datos confidenciales ingresan a modelos de IA | Fuga de datos no detectable, violacion de GDPR/HIPAA |
| Los pipelines de CI/CD no verifican que contexto envian a herramientas de IA | Exposicion de credenciales, configuraciones internas, datos de clientes |
| Las decisiones de sanitizacion son opacas (el modelo decide, nadie sabe por que) | No auditables, no defendibles ante compliance |
| Los agentes LLM no tienen forma estandar de verificar la seguridad del contexto que consumen | El agente opera sobre datos no validados |
| Las soluciones existentes requieren enviar datos a SaaS externos para procesarlos | Incompatible con entornos regulados y air-gapped |
| Las organizaciones multi-tenant no pueden aislar datos entre divisiones | Contaminacion cruzada de datos sensibles |

---

## 3. Usuarios y audiencias

### 3.1 Usuarios humanos

| Perfil | Rol en SafeContext | Interaccion principal | Necesidad critica |
|---|---|---|---|
| **Desarrollador** | `viewer` | UI web, pipeline gate, pagina `/scan` | Saber que fue detectado y por que antes de que su codigo llegue a produccion |
| **Arquitecto / Tech Lead** | `policy_editor` | Revision de politicas, excepciones, waivers | Control sobre reglas de sanitizacion y umbrales de confianza |
| **Compliance / Seguridad** | `reviewer` | Audit trail, exportacion de evidencia, pagina `/audit` | Evidencia inmutable de cada decision para auditorias |
| **Operador / SRE** | `admin` | Monitoreo, runbooks, DR, pagina `/admin` | Observabilidad, gestion de tenants y recuperacion ante fallas |
| **CISO / CTO** | `admin` | Reportes de compliance, dashboards | Demostrar ante auditores que los controles existen y funcionan |

> **Modelo de roles**: SafeContext define exactamente 4 roles — `viewer`, `reviewer`, `policy_editor`, `admin`. Detalle completo en `manuals/08_ROLES_Y_PERMISOS.md`.

### 3.2 Consumidores agente (no humanos)

| Agente | Modo de integracion | Caso de uso tipico |
|---|---|---|
| **Claude (Anthropic)** | MCP Server | Verificar contexto antes de procesar documentos |
| **GitHub Copilot / Codex** | MCP Server | Gate de sanitizacion antes de generar codigo sobre datos sensibles |
| **GitHub Actions** | MCP Server / REST API | Pipeline gate: bloquear merge si el contexto no esta sanitizado |
| **GitLab CI / Azure DevOps** | MCP Server / REST API | Mismo patron que GitHub Actions |
| **Agente custom del cliente** | MCP Server | Cualquier agente LLM del cliente que implemente el protocolo MCP |

### 3.3 Agentes internos de SafeContext

Los agentes internos son la **unidad de capacidad** del producto. No son integraciones externas. Son componentes propios, especializados, que corren localmente.

| Agente interno | Responsabilidad | Autonomia |
|---|---|---|
| **Detector** | Identificar PII, secretos, datos sensibles en documentos (Presidio + spaCy + RegexDetector) | Alta — opera sin intervencion humana en casos claros |
| **Sanitizador** | Redactar, enmascarar o eliminar contenido detectado. Incluye rescan post-sanitizacion | Alta — ejecuta segun politica versionada |
| **Clasificador** | Asignar nivel de sensibilidad al documento y sus secciones | Alta |
| **Auditor** | Registrar cada decision con trace_id, policy_version, artifact_digest, actor | Total — nunca omite registro |
| **Revisor** | Escalar a revision humana cuando confianza < umbral o impacto > threshold | Opera como gate — bloquea hasta aprobacion |

**Principio invariante**: ninguna logica de negocio vive en la capa UI ni en el MCP Server. UI y MCP son exclusivamente capas de entrega. Los agentes internos son la unica fuente de capacidad.

---

## 4. Modelo funcional

### 4.1 Capacidades core

| Capacidad | Descripcion | Garantia enterprise |
|---|---|---|
| **Deteccion** | Identificacion de PII, secretos, datos regulados usando reglas deterministicas (RegexDetector) + NLP/ML (Presidio/spaCy) | Recall >= 0.98 en clases criticas. Golden corpus de 200+ samples en CI |
| **Sanitizacion** | Redaccion, enmascaramiento o eliminacion con justificacion explicita. Rescan automatico post-sanitizacion | Cada redaccion lleva rule_id, detector, confianza, version de politica |
| **Clasificacion** | Nivel de sensibilidad por documento y seccion | Explicable, versionado, auditable |
| **Gobierno de politicas** | Reglas versionadas, testeadas, desplegadas por pipeline. Politicas por tenant | Policy-as-code con OPA/Rego. Hot-reload sin reinicio |
| **Revision humana** | Gate obligatorio para hallazgos de alta criticidad o baja confianza | Aprobacion registrada con actor, timestamp, trace_id. SoD enforced |
| **Waivers** | Excepciones temporales a reglas de deteccion con aprobacion, expiracion y trazabilidad | OPA consulta waivers activos. Waivers expirados no aplican |
| **Auditoria inmutable** | Registro de toda operacion critica con cadena de custodia criptografica | trace_id + artifact_digest + policy_version + actor + chain_hash + firma digital |
| **Multi-tenancy** | Aislamiento completo de datos y politicas por tenant | RLS PostgreSQL, OPA per-tenant, quotas, rate limiting |
| **Compliance** | Reportes auto-generados SOC 2 / ISO 27001 / GDPR. Purga GDPR con certificados firmados | Evidencia presentable ante auditores externos |
| **SIEM** | Exportacion de eventos de seguridad en CEF/LEEF/JSON via webhook o syslog | Configurable por tenant |
| **Operacion offline** | Todas las capacidades funcionan sin dependencias externas | Air-gapped completo |

### 4.2 Superficies de consumo

```
+---------------------------------------------------------+
|                      SafeContext Core                    |
|                                                         |
|   Agentes internos (locales, especializados)            |
|   Detector - Sanitizador - Clasificador - Auditor -     |
|   Revisor                                               |
|                                                         |
+---------------------------+-----------------------------+
|    UI Web                 |         MCP Server          |
|    (Next.js + TS)         |    (protocolo MCP estandar) |
|                           |                             |
|  Consume agentes          |  Expone agentes como tools: |
|  internos para            |  - Claude / Codex / LLM    |
|  operacion humana         |  - GitHub Actions / CI     |
|                           |  - Agentes custom          |
+---------------------------+-----------------------------+
```

**La UI no es una superficie separada en terminos de capacidad.** Es un cliente privilegiado que consume los mismos agentes internos que el MCP Server expone. Esto garantiza paridad funcional entre interfaces.

### 4.3 MCP Server — herramientas expuestas

| Tool MCP | Input | Output | Scopes requeridos |
|---|---|---|---|
| `safecontext.scan` | documento, politica | hallazgos con explicacion, confianza | `scan:read` |
| `safecontext.sanitize` | trace_id, tipo de redaccion | documento sanitizado + redaction_map | `scan:read` |
| `safecontext.classify` | documento | nivel de sensibilidad + justificacion | `scan:read` |
| `safecontext.approve` | hallazgo_id + decision | aprobacion registrada | `review:write` |
| `safecontext.audit` | trace_id | evidencia completa de la operacion | `audit:read` |
| `safecontext.policy.get` | nombre de politica | politica activa versionada | `scan:read` |

### 4.4 Flujos principales

**Flujo humano (UI)**:
```
Usuario pega documento -> POST /v1/scan -> workers detectan (async) ->
si critico: escala a revision -> Reviewer aprueba/rechaza con justificacion ->
audit trail inmutable -> documento sanitizado disponible
```

**Flujo agente externo (MCP)**:
```
Agente invoca safecontext.scan -> detector analiza ->
hallazgos con explicacion completa -> agente invoca safecontext.sanitize ->
documento sanitizado + redaction_map + trazabilidad
```

**Flujo pipeline CI/CD**:
```
Push/PR -> GitHub Action -> safecontext.scan ->
si hallazgos criticos: pipeline bloqueado + reporte en PR ->
si limpio: pipeline continua con evidencia de escaneo adjunta
```

---

## 5. Requisitos funcionales

### 5.1 Superficie UI Web

| ID | Requisito | Prioridad | Fase | Estado |
|---|---|---|---|---|
| RF-UI-01 | El usuario puede subir un documento y ver hallazgos con explicacion completa | Must | F1 | ✅ |
| RF-UI-02 | El usuario puede ver el documento sanitizado con redaction_map visual | Must | F1 | ✅ |
| RF-UI-03 | El revisor puede aprobar o rechazar hallazgos de baja confianza con justificacion registrada | Must | F1 | ✅ |
| RF-UI-04 | El Tech Lead puede crear, editar y versionar politicas OPA/Rego desde la UI | Should | F2 | ✅ (via waivers + admin) |
| RF-UI-05 | Compliance puede exportar el audit trail completo de una operacion dado un trace_id | Must | F2 | ✅ |
| RF-UI-06 | El operador tiene dashboard con metricas de calidad del sanitizado, latencia y errores | Should | F2 | ✅ |
| RF-UI-07 | SSO/MFA obligatorio para acceso a la UI | Must | F4 | ✅ |
| RF-UI-08 | Segregacion de funciones: roles Viewer, Reviewer, PolicyEditor, Admin | Must | F4 | ✅ |
| RF-UI-09 | Panel de administracion para gestion de tenants, politicas, SIEM, waivers y retencion GDPR | Must | F6 | ✅ |
| RF-UI-10 | Selector de tenant en la barra de navegacion para entornos multi-tenant | Must | F6 | ✅ |

### 5.2 Superficie MCP Server

| ID | Requisito | Prioridad | Fase | Estado |
|---|---|---|---|---|
| RF-MCP-01 | Exponer `safecontext.scan` con input documento y output hallazgos explicados | Must | F1 | ✅ |
| RF-MCP-02 | Exponer `safecontext.sanitize` con output documento sanitizado + redaction_map | Must | F1 | ✅ |
| RF-MCP-03 | Exponer `safecontext.classify` con output nivel de sensibilidad por seccion | Must | F1 | ✅ |
| RF-MCP-04 | Exponer `safecontext.audit` para recuperar evidencia de operacion por trace_id | Must | F2 | ✅ |
| RF-MCP-05 | Exponer `safecontext.policy.get` para obtener politica activa versionada | Should | F2 | ✅ |
| RF-MCP-06 | Autenticacion OAuth 2.1/OIDC con PKCE obligatoria para todo cliente MCP | Must | F3 | ✅ |
| RF-MCP-07 | Rate limiting configurable por cliente/agente y por tenant | Must | F3 | ✅ |
| RF-MCP-08 | Audit trail por identidad de agente (no solo por usuario humano) | Must | F3 | ✅ |
| RF-MCP-09 | Versionado semantico de tools — los clientes pueden fijar version de tool | Should | F4 | ✅ |
| RF-MCP-10 | `safecontext.approve` para que agentes con permisos delegados registren aprobaciones | Should | F4 | ✅ |
| RF-MCP-11 | Consent management: scopes `scan:read`, `audit:read`, `review:write` validados por tool | Must | F4 | ✅ |

### 5.3 Superficie Pipeline CI/CD

| ID | Requisito | Prioridad | Fase | Estado |
|---|---|---|---|---|
| RF-CI-01 | GitHub Action oficial que invoca safecontext.scan en PR/push | Must | F1 | ✅ |
| RF-CI-02 | Pipeline retorna pass/block con reporte de hallazgos adjunto al PR | Must | F1 | ✅ |
| RF-CI-03 | Gate de aprobacion humana en pipeline para hallazgos criticos | Must | F2 | ✅ |
| RF-CI-04 | Autenticacion OIDC — sin secretos estaticos en CI | Must | F3 | ✅ |
| RF-CI-05 | SBOM y firma de artefactos como parte del pipeline | Must | F3 | ✅ |
| RF-CI-06 | Soporte para GitLab CI y Azure DevOps | Should | F4 | ✅ |

### 5.4 Agentes internos

| ID | Requisito | Prioridad | Fase | Estado |
|---|---|---|---|---|
| RF-AG-01 | Detector identifica PII, secretos, datos regulados usando reglas deterministicas + NLP/ML | Must | F1 | ✅ |
| RF-AG-02 | Sanitizador redacta con justificacion: rule_id, detector, confianza, policy_version | Must | F1 | ✅ |
| RF-AG-03 | Clasificador asigna nivel de sensibilidad por documento y seccion | Must | F1 | ✅ |
| RF-AG-04 | Auditor registra toda operacion critica de forma inmutable en PostgreSQL | Must | F1 | ✅ |
| RF-AG-05 | Revisor escala a revision humana cuando confianza < umbral configurable | Must | F1 | ✅ |
| RF-AG-06 | Todos los agentes operan sin dependencias de internet | Must | F1 | ✅ |
| RF-AG-07 | Los agentes soportan politicas hot-reload sin reinicio del servicio | Should | F2 | ✅ |
| RF-AG-08 | El Detector expone metricas de recall y false positive rate por clase | Must | F2 | ✅ |
| RF-AG-09 | Rescan automatico post-sanitizacion para detectar fugas residuales | Must | F2 | ✅ |
| RF-AG-10 | RegexDetector como capa deterministica pre-ML (API keys, JWT, connection strings) | Must | F2 | ✅ |

---

## 6. Requisitos no funcionales

### 6.1 Seguridad

| ID | Requisito | Meta Enterprise | Estado |
|---|---|---|---|
| RNF-SEC-01 | Zero Trust: autenticacion explicita en cada operacion entre componentes | 100% de operaciones autenticadas | ✅ |
| RNF-SEC-02 | Sin secretos estaticos en repositorios ni CI/CD | 0 secretos estaticos | ✅ |
| RNF-SEC-03 | TLS en todas las comunicaciones internas y externas | 100% | ✅ |
| RNF-SEC-04 | Row-Level Security en PostgreSQL por tenant | Habilitado y auditado en 5 tablas | ✅ |
| RNF-SEC-05 | Cifrado en reposo para artefactos en MinIO (SSE) | 100% de artefactos | ✅ |
| RNF-SEC-06 | KMS para gestion de claves (OpenBao Transit) | Rotacion sin downtime | ✅ |
| RNF-SEC-07 | MFA obligatorio para acceso humano | 100% via Keycloak | ✅ |

### 6.2 Compliance

| ID | Requisito | Marco | Estado |
|---|---|---|---|
| RNF-COM-01 | Audit trail inmutable con trace_id + artifact_digest + actor + policy_version + chain_hash | GDPR, HIPAA, SOC2 | ✅ |
| RNF-COM-02 | Exportacion de evidencia en SARIF, JSON firmado | GDPR Art. 30, HIPAA | ✅ |
| RNF-COM-03 | Retencion de datos configurable por tenant | GDPR, HIPAA | ✅ |
| RNF-COM-04 | Borrado verificable con certificado firmado (GDPR purge) | GDPR Art. 17 | ✅ |
| RNF-COM-05 | Segregacion de funciones con roles auditados | SOC2, HIPAA | ✅ |
| RNF-COM-06 | SBOM firmado por imagen de contenedor (CycloneDX + cosign) | SLSA, SSDF | ✅ |
| RNF-COM-07 | Firma de artefactos verificable | SLSA Level 3 | ✅ |
| RNF-COM-08 | Reportes de compliance auto-generados (SOC 2, ISO 27001, GDPR) | Multi-framework | ✅ |

### 6.3 Disponibilidad y resiliencia

| ID | Requisito | Meta Enterprise | Estado |
|---|---|---|---|
| RNF-RES-01 | Disponibilidad del servicio de scan | 99.9% con SLA | ✅ |
| RNF-RES-02 | RTO ante falla de base de datos | < 15 min verificado en DR drill | ✅ |
| RNF-RES-03 | RPO maximo | < 5 min con WAL archiving | ✅ |
| RNF-RES-04 | Backup probado | Semanal con DR drill trimestral | ✅ |

### 6.4 Performance

| ID | Requisito | Meta |
|---|---|---|
| RNF-PERF-01 | Latencia p95 de safecontext.scan para documento < 1MB | < 5 segundos |
| RNF-PERF-02 | Latencia p95 de API | < 500ms (excluye procesamiento ML) |
| RNF-PERF-03 | Throughput minimo sostenido | 100 documentos/hora en single-node |

### 6.5 Operacion offline / air-gapped

| ID | Requisito | Estado |
|---|---|---|
| RNF-OFFL-01 | Instalacion completa sin acceso a internet | ✅ |
| RNF-OFFL-02 | Actualizacion y rollback documentados y probados sin internet | ✅ |
| RNF-OFFL-03 | Registry privado de imagenes de contenedor (Harbor) | ✅ |
| RNF-OFFL-04 | Runners/agentes CI/CD self-hosted | ✅ |
| RNF-OFFL-05 | Modelos NLP/ML descargados y empaquetados localmente | ✅ |

---

## 7. Arquitectura

### 7.1 Vista de componentes

```
+---------------------------------------------------------------------+
|                         SafeContext Platform                         |
|                                                                     |
|  +--------------+    +------------------------------------------+   |
|  |  Next.js UI  |    |            FastAPI Backend                |   |
|  |  TypeScript  |--->|  +-----------+  +------------------+     |   |
|  |  Tailwind    |    |  | REST API  |  |   MCP Server     |     |   |
|  +--------------+    |  | /v1/...   |  |  /v1/mcp/tools   |     |   |
|                      |  +-----+-----+  +--------+---------+     |   |
|  Clientes MCP ------>|        |                  |               |   |
|  (Claude, Codex,     |        +--------+---------+               |   |
|   GitHub Actions)    |                 |                         |   |
|                      |        +--------v---------+               |   |
|                      |        |  Policy Engine   |               |   |
|                      |        |  OPA / Rego      |               |   |
|                      |        +--------+---------+               |   |
|                      |                 |                         |   |
|                      |    +------------v-----------------+       |   |
|                      |    |      Agent Dispatcher        |       |   |
|                      |    +--+------+------+------+------+       |   |
|                      +-------+------+------+------+--------------+   |
|                              |      |      |      |                  |
|  +---------------------------v------v------v------v--------------+   |
|  |                    Workers (Dramatiq)                         |   |
|  |  +----------+ +------------+ +--------------+ +----------+   |   |
|  |  | Detector | |Sanitizador | | Clasificador | | Auditor  |   |   |
|  |  +----+-----+ +-----+------+ +------+-------+ +----+-----+   |   |
|  |       |             |               |               |         |   |
|  |  +----v-------------v---------------v---------------v-----+   |   |
|  |  |                    Revisor (gate humano)                |   |   |
|  |  +--------------------------------------------------------+   |   |
|  +----------------------------------------------------------------+   |
|                                                                     |
|  +--------------+  +---------------+  +--------------------------+  |
|  |  PostgreSQL  |  |     Redis     |  |         MinIO            |  |
|  |  (registro)  |  |  (broker/     |  |  (artefactos + evidencia)|  |
|  |  pgAudit     |  |   cache)      |  |  WORM + SSE              |  |
|  |  RLS         |  |               |  |                          |  |
|  +--------------+  +---------------+  +--------------------------+  |
|                                                                     |
|  +------------------------------+  +----------------------------+   |
|  |  Keycloak (OIDC/MFA/SSO)    |  |  OpenBao (KMS/Transit)     |   |
|  +------------------------------+  +----------------------------+   |
|                                                                     |
|  +---------------------------------------------------------------+  |
|  |  OpenTelemetry + Prometheus + Grafana + Loki + Tempo          |  |
|  +---------------------------------------------------------------+  |
+---------------------------------------------------------------------+
```

### 7.2 Modelo de despliegue

**Docker Compose (desarrollo y single-node)**:
```
docker compose up                    # Stack minimo (API, UI, workers, PG, Redis, MinIO, OTel)
docker compose --profile auth up     # + Keycloak + OpenBao
docker compose --profile full up     # Todo incluido
```

14 servicios, 3 redes (backend, frontend, observability).

**Kubernetes (produccion / HA)**:
- 30 manifiestos K8s generados desde Compose Bridge
- HPA en API y workers
- PodDisruptionBudget para API y PostgreSQL
- NetworkPolicy deny-all por defecto
- CloudNativePG para HA y WAL archiving
- SecurityContext: `runAsNonRoot`, `capabilities.drop: [ALL]`

**Air-gapped**:
- Harbor como registry privado con imagenes firmadas
- Runners CI/CD self-hosted sin internet
- Modelos NLP/ML empaquetados en imagen
- Bundle de actualizacion offline con rollback probado

---

## 8. Modelo de datos

### 8.1 Schema core

```sql
-- Tenants (multi-tenancy)
tenants (
  id              UUID PRIMARY KEY,
  name            VARCHAR(255) NOT NULL,
  slug            VARCHAR(64) UNIQUE NOT NULL,
  plan            VARCHAR(32) DEFAULT 'starter',    -- starter | professional | enterprise
  contact_email   VARCHAR(255),
  is_active       BOOLEAN DEFAULT true,
  max_scans_day   INTEGER DEFAULT 100,
  max_doc_size_kb INTEGER DEFAULT 5120,
  policy_config   JSONB DEFAULT '{}',               -- confidence_overrides, severity_overrides, blocked_entity_types
  siem_config     JSONB DEFAULT '{}',               -- enabled, format, webhook_url, syslog_host, etc.
  retention_days  INTEGER DEFAULT 365,
  created_at      TIMESTAMPTZ DEFAULT now()
)

-- Operaciones (RANGE PARTITIONED by created_at, monthly)
operations (
  id              UUID,
  trace_id        UUID NOT NULL,
  actor_id        UUID NOT NULL,        -- humano o agente (sub del JWT)
  actor_type      TEXT NOT NULL,         -- 'human' | 'mcp_agent' | 'pipeline'
  tenant_id       UUID NOT NULL,
  document_id     UUID NOT NULL,
  artifact_digest TEXT NOT NULL,         -- SHA-256 del documento original
  policy_version  TEXT NOT NULL,
  status          TEXT NOT NULL,         -- 'pending' | 'completed' | 'escalated' | 'approved' | 'rejected'
  chain_hash      TEXT,                  -- hash encadenado para cadena de custodia
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ,
  PRIMARY KEY (id, created_at)           -- PK compuesta para particionado
)

-- Hallazgos
findings (
  id              UUID PRIMARY KEY,
  operation_id    UUID NOT NULL,
  detector        TEXT NOT NULL,         -- 'presidio.EMAIL' | 'regex.API_KEY' | etc.
  rule_id         TEXT NOT NULL,
  span_start      INT NOT NULL,
  span_end        INT NOT NULL,
  confidence      FLOAT NOT NULL,        -- 0.0 - 1.0
  severity        TEXT NOT NULL,         -- 'low' | 'medium' | 'high' | 'critical'
  explanation     JSONB NOT NULL,
  UNIQUE (operation_id, rule_id, span_start, span_end)
)

-- Redacciones aplicadas
redactions (
  id              UUID PRIMARY KEY,
  finding_id      UUID,
  operation_id    UUID NOT NULL,
  redaction_type  TEXT NOT NULL,         -- 'mask' | 'remove' | 'replace'
  policy_version  TEXT NOT NULL,
  applied_at      TIMESTAMPTZ DEFAULT now(),
  approved_by     UUID
)

-- Artefactos de evidencia (referencia a MinIO)
artifacts (
  id              UUID PRIMARY KEY,
  operation_id    UUID NOT NULL,
  artifact_type   TEXT NOT NULL,         -- 'original' | 'sanitized' | 'audit_export'
  minio_key       TEXT NOT NULL,
  digest          TEXT NOT NULL,         -- SHA-256
  worm_locked     BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT now()
)

-- Waivers (excepciones de politica)
waivers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,
  rule_id         VARCHAR(128) NOT NULL,
  entity_pattern  TEXT NOT NULL,         -- regex
  justification   TEXT NOT NULL,
  approved_by     UUID NOT NULL,
  status          VARCHAR(32) DEFAULT 'active',  -- 'active' | 'expired' | 'revoked'
  expires_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now(),
  metadata        JSONB DEFAULT '{}'
)

-- Outbox para coordinacion PostgreSQL -> Redis
outbox (
  id              UUID PRIMARY KEY,
  event_type      TEXT NOT NULL,
  payload         JSONB NOT NULL,
  processed       BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT now()
)
```

### 8.2 Migraciones Alembic (11 total)

| # | Revision | Descripcion |
|---|---|---|
| 0001-0004 | — | Schema base, indices, outbox |
| 0005 | `3f8a1c9d2e47` | Particionado RANGE MONTHLY de `operations`. PK compuesta `(id, created_at)` |
| 0006 | `b2c3d4e5f6a7` | Tabla `waivers` |
| 0007 | — | Unique constraint en `findings` |
| 0008 | — | Tabla `tenants` con modelo multi-tenant. Backfill tenant default |
| 0009 | — | RLS (Row-Level Security) en 5 tablas. `FORCE ROW LEVEL SECURITY` |
| 0010 | — | Columna `chain_hash` en `operations` |
| 0011 | — | Columnas `policy_config` (JSONB), `siem_config` (JSONB), `retention_days` (Integer) en `tenants` |

### 8.3 RLS (Row-Level Security)

Habilitado en: `operations`, `waivers`, `findings`, `redactions`, `artifacts`.
Mecanismo: `SET LOCAL app.current_tenant_id` en cada request via `get_tenant_db` dependency.
Child tables (`findings`, `redactions`, `artifacts`) usan sub-select via `operation_id`.

---

## 9. Decisiones de arquitectura (ADRs)

| ADR | Decision | Justificacion |
|---|---|---|
| ADR-001 | PostgreSQL como unico sistema de registro | Redis ofrece velocidad pero pierde datos en failover. PG es la unica fuente de verdad |
| ADR-002 | Redis exclusivamente como broker y cache efimero | Puede perder datos sin impacto en integridad. Nunca fuente de verdad |
| ADR-003 | MCP Server implementado sobre FastAPI | Modulo de FastAPI, no proceso separado. Comparte auth y observabilidad |
| ADR-004 | Agentes internos como unica fuente de capacidad | UI y MCP invocan los mismos workers. Sin logica duplicada por superficie |
| ADR-005 | OPA/Rego para policy-as-code | Politicas versionadas, testeables, desplegables por pipeline, sin recompilacion |
| ADR-006 | Compose para desarrollo; K8s para Enterprise/HA | Umbral de migracion: multi-instancia, HPA, multi-tenant, exigencia regulatoria |
| ADR-007 | Dramatiq sobre Redis como broker de workers | Mas simple que Celery. Umbral de migracion: si se requieren chord/group/chain |
| ADR-008 | MinIO con WORM + SSE para artefactos | Object locking inmutable. Cifrado del lado servidor |
| ADR-009 | OpenTelemetry + Prometheus para observabilidad | Estandar de industria, vendor-neutral |
| ADR-010 | Presidio + spaCy como detectores base, interfaz abstraida | DetectorInterface permite sustituir sin cambiar flujo |
| ADR-011 | Port & Adapter para Redis y MinIO | BrokerPort, CachePort, StoragePort. Swap = solo cambiar adapter + `.env` |
| ADR-012 | Documento sanitizado como artefacto del pipeline | Nunca se modifica el original. Toda redaccion genera artefacto nuevo |
| ADR-013 | Evaluacion de storage provider (MinIO CE -> AIStor) | MinIO CE pinned a RELEASE.2025-09-07. AIStor como upgrade path. S3_* vars |

ADRs completos en `docs/adr/ADR-NNN-*.md`.

---

## 10. Stack tecnologico

| Componente | Tecnologia | Version | Lock-in | Nota |
|---|---|---|---|---|
| Backend | FastAPI + Python | 3.14 | Bajo | Soporte hasta 2029 |
| Frontend | Next.js + TypeScript | 16.2 / TS 5 | Medio | App Router, React 19, Node 24.16.0 |
| Base de datos | PostgreSQL | 18.4 | Bajo | JSONB + RLS + pgAudit + particionado |
| Cola/Workers | Redis + Dramatiq | Redis 7.4 | Bajo | Broker efimero unicamente |
| Almacenamiento | MinIO (StoragePort) | RELEASE.2025-09-07 | Bajo | S3-compatible, swap solo en `.env` |
| Motor de politicas | OPA / Rego | 1.4.0 | Medio | Policy-as-code versionado |
| Observabilidad | OTel + Prometheus + Grafana | Prometheus v3.11.3, Grafana 13.0.1 | Ninguno | + Loki (logs) + Tempo (traces) |
| Proxy reverso | nginx | 1.28 | Bajo | TLS, rate limiting, security headers |
| Auth / SSO | Keycloak | 26.2 | Bajo | OIDC + MFA, estandar abierto |
| KMS | OpenBao | 2.5.4 (MPL 2.0) | Bajo | Fork Vault, Linux Foundation |
| Registry | Harbor | Self-hosted | Bajo | Air-gapped ready |
| NLP/PII | Presidio + spaCy en_core_web_lg | 2.2.x | Bajo | Interfaz abstraida (ADR-010) |
| Orquestacion | Docker Compose -> K8s | — | Bajo | Compose F1-F5; K8s F3+ |

---

## 11. Principios no negociables

1. **PostgreSQL es el unico sistema de registro**. Redis es efimero — nunca fuente de verdad para decisiones, auditoria o jobs.
2. **Los agentes internos son la unica fuente de capacidad**. UI y MCP son capas de entrega sin logica de negocio.
3. **Toda decision es explicable**. Ningun resultado sale sin rule_id, detector, confianza, policy_version.
4. **Toda operacion critica genera audit trail**. trace_id + artifact_digest + actor + timestamp + chain_hash — sin excepciones.
5. **El producto opera sin internet**. Ningun flujo critico depende de SaaS externo.
6. **Las politicas son codigo**. Versionadas, testeadas, desplegadas por pipeline, evaluadas por OPA.
7. **La revision humana es un gate, no una opcion**. Para hallazgos de alta criticidad o baja confianza, el flujo se bloquea hasta aprobacion.
8. **Los originales nunca se modifican**. Toda redaccion genera artefacto nuevo; el original se preserva en WORM.
9. **Segregacion de funciones es automatica**. Quien escanea no puede aprobar sus propios hallazgos. No es configurable ni eludible.
10. **Multi-tenancy con aislamiento real**. RLS en PostgreSQL, politicas OPA por tenant, quotas y rate limiting por tenant.

---

## 12. Fases y criterios de aceptacion

### Resumen de fases

| Fase | Objetivo | Estado |
|---|---|---|
| **F1** Base segura | Estructura tecnica, observabilidad, pipeline gate funcional | ✅ Completada |
| **F2** Producto endurecido | Operacion repetible, backup/restore, auditoria, jobs resilientes | ✅ Completada |
| **F3** Supply chain | Cadena de suministro verificable, 0 secretos estaticos, deploy gate | ✅ Completada |
| **F4** Enterprise operativo | SSO/MFA, SLOs, DR verificado, segregacion de funciones | ✅ Completada |
| **F5** Desconectado regulado | Instalacion, operacion, actualizacion y rollback sin internet | ✅ Completada |
| **F6** Enterprise regulado | Multi-tenant, evidencias firmadas, compliance repetible, admin module | ✅ Completada |

### Gates de salida verificados

Cada fase tiene criterios de aceptacion binarios documentados. Todos los gates F1->F2->F3->F4->F5->F6 fueron verificados. El detalle completo de criterios por entregable esta en `docs/ROADMAP.md` secciones 5-6.

### Backlog de mejora T1-T10

Las 10 tareas del replanteo de madurez (SARIF, actor_id JWT, rescan, RegexDetector, waivers, golden corpus, particionado, OAuth 2.1 PKCE, consent management, version upgrades) fueron completadas el 2026-05-22. Detalle en `docs/ROADMAP.md` seccion 7.

### F6 Enterprise regulado (completado 2026-05-24)

| Bloque | Tareas | Estado |
|---|---|---|
| F6-A Multi-tenancy | 6 tareas: modelo tenant, RLS, OPA per-tenant, quotas, admin API, UI selector | ✅ |
| F6-B Evidencias firmadas | 4 tareas: TSA RFC 3161, chain hash, firma Transit, WORM retention | ✅ |
| F6-C Compliance repetible | 6 tareas: SBOM firmado, compliance checks, reportes SOC2/ISO/GDPR, pen-test CI, GDPR purge, SIEM | ✅ |
| Admin Module | 12 entregables: 3 endpoints, 4 paginas UI, 3 test suites, manual, ROADMAP | ✅ |

---

## 13. Modelo de madurez

| Nivel | Nombre | Criterio | Estado |
|---|---|---|---|
| 0 | Idea | Vision sin arquitectura | ✅ |
| 1 | Diseno conceptual | Modulos definidos, stack elegido | ✅ |
| 2 | Diseno controlado | ADRs, bounded contexts, roadmap, criterios de aceptacion | ✅ |
| 3 | Plataforma funcional | Core deterministico, UI, politicas, DevSecOps minimo | ✅ |
| 4 | Piloto enterprise | Auditoria completa, OIDC, observabilidad, MCP seguro, offline | ✅ |
| **5** | **Enterprise regulado** | **Multi-tenant, evidencias firmadas, hardening, compliance repetible** | **✅ Actual** |

**Madurez actual: 5 / 5**

---

## 14. Fuera de alcance

- SafeContext **no** es un firewall de red ni un WAF.
- SafeContext **no** gestiona el ciclo de vida de modelos de IA (MLOps/LLMOps) — solo gobierna el contexto que les llega.
- SafeContext **no** reemplaza un DLP corporativo — es complementario y especializado en pipelines de IA.
- SafeContext **no** genera respuestas de IA — es un gate de entrada, no un modelo.
- La UI **no** incluye capacidades de edicion de documentos — solo visualizacion, revision y aprobacion (preservar cadena de custodia).
- SafeContext **no** es un escaner de secretos (detect-secrets, truffleHog) — detecta datos sensibles en documentos de negocio y contextos de IA.

---

## Documentos relacionados

| Documento | Proposito |
|---|---|
| `ROADMAP.md` | Estado detallado de implementacion, flags por entregable |
| `manuals/01-09` | Manuales operativos por audiencia |
| `adr/ADR-001..013` | Decisiones de arquitectura completas |
| `GLOSSARY.md` | Glosario canonico de terminos |
| `CLAUDE.md` | Instrucciones para agentes Claude Code |
| `runbooks/` | Runbooks operativos (DR, DLQ, rotacion de claves) |

---

*Consolidado a partir de: DOC-0_UNIFIED.md v0.2.0, DOC-1_PRD.md v0.1.0, DOC-2_SAD.md v0.1.0, DOC-3_SPEC.md v0.2.0, ROADMAP.md v1.2.0*
*Verificado contra estado real del codigo: 2026-05-25*
*Proxima revision: antes del primer piloto enterprise con cliente externo*
