# SafeContext — Manual Técnico de Arquitectura
**Versión**: 1.0.0 | **Fecha**: 2026-05-18 | **Audiencia**: Desarrolladores, Arquitectos, AppSec

---

## Tabla de contenidos

1. [Visión general](#1-visión-general)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Arquitectura de componentes](#3-arquitectura-de-componentes)
4. [Flujos principales](#4-flujos-principales)
5. [Modelo de datos](#5-modelo-de-datos)
6. [Decisiones de arquitectura (ADRs resumen)](#6-decisiones-de-arquitectura-adrs-resumen)
7. [Seguridad](#7-seguridad)
8. [Observabilidad](#8-observabilidad)
9. [Extensibilidad](#9-extensibilidad)
10. [Glosario técnico](#10-glosario-técnico)

---

## 1. Visión general

SafeContext es una plataforma Enterprise-grade de sanitización, clasificación y gobierno de documentos y datos sensibles, diseñada para ser consumida tanto por humanos como por agentes de inteligencia artificial. Su propósito central es garantizar que ningún documento sensible llegue a un modelo de IA, pipeline de CI/CD o sistema externo sin haber pasado por un proceso verificable, auditable y explicable de detección, sanitización y aprobación.

La arquitectura del sistema gira en torno a cinco agentes internos especializados — Detector, Sanitizador, Clasificador, Auditor y Revisor — que encapsulan toda la lógica de negocio. Las superficies de consumo (UI web y MCP Server) son exclusivamente capas de entrega que invocan a estos agentes. Este diseño garantiza paridad funcional entre interfaces: la misma cadena de procesamiento que ejecuta un desarrollador desde la UI es idéntica a la que invoca un agente LLM via MCP.

SafeContext expone sus capacidades como MCP Server, lo que permite que cualquier agente LLM compatible (Claude, Codex, GitHub Copilot, entre otros) consuma la plataforma como herramienta nativa sin lock-in de interfaz. Opera con modelos NLP/ML locales (Presidio + spaCy), garantizando compatibilidad con entornos air-gapped y despliegues regulados donde los datos no pueden salir del perímetro. Toda decisión es explicable, auditable e inmutable: cada operación genera un `trace_id`, un `artifact_digest`, una `policy_version` y un registro permanente en PostgreSQL.

### Diagrama de componentes

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SafeContext Platform                        │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │  Next.js UI  │    │            FastAPI Backend               │  │
│  │  TypeScript  │───▶│  ┌─────────────┐  ┌──────────────────┐  │  │
│  │  Tailwind    │    │  │  REST API   │  │   MCP Server     │  │  │
│  │  shadcn/ui   │    │  │  /v1/...    │  │  /v1/mcp/tools   │  │  │
│  └──────────────┘    │  └──────┬──────┘  └────────┬─────────┘  │  │
│                       │         │                   │            │  │
│  Clientes MCP ───────▶│         └─────────┬─────────┘           │  │
│  (Claude, Codex,      │                   │                     │  │
│   GitHub Actions)     │         ┌─────────▼─────────┐          │  │
│                       │         │   Policy Engine   │          │  │
│                       │         │   OPA / Rego      │          │  │
│                       │         └─────────┬─────────┘          │  │
│                       │                   │                     │  │
│                       │    ┌──────────────▼──────────────────┐  │  │
│                       │    │         Agent Dispatcher        │  │  │
│                       │    └──┬───────┬──────┬───────┬───────┘  │  │
│                       └───────┼───────┼──────┼───────┼──────────┘  │
│                               │       │      │       │              │
│  ┌────────────────────────────▼───────▼──────▼───────▼──────────┐  │
│  │                    Workers (Dramatiq)                         │  │
│  │  ┌──────────┐ ┌────────────┐ ┌──────────────┐ ┌──────────┐  │  │
│  │  │ Detector │ │Sanitizador │ │ Clasificador │ │ Auditor  │  │  │
│  │  └────┬─────┘ └─────┬──────┘ └──────┬───────┘ └────┬─────┘  │  │
│  │       │             │               │               │         │  │
│  │  ┌────▼─────────────▼───────────────▼───────────────▼─────┐  │  │
│  │  │                    Revisor (gate humano)                │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │  PostgreSQL  │  │     Redis     │  │         MinIO            │ │
│  │  (registro)  │  │  (broker/     │  │  (artefactos + evidencia)│ │
│  │  pgAudit     │  │   cache)      │  │  WORM + SSE              │ │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘ │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            OpenTelemetry + Prometheus + Grafana              │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Diferencial competitivo

| Característica | SafeContext | Escáner de secretos convencional | SaaS de DLP |
|---|---|---|---|
| Gobernanza de contexto para IA | Si — propósito central | No | Parcial |
| Operación air-gapped | Si — todos los flujos | Parcial | No |
| Explicabilidad por hallazgo | Si — rule_id, detector, confianza, policy_version | No | Raramente |
| MCP Server nativo | Si | No | No |
| Revisión humana como gate | Si — bloqueo hasta aprobación | No | Opcional |
| Policy-as-code versionado | Si — OPA/Rego | No | No |
| Audit trail inmutable | Si — PostgreSQL + MinIO WORM | No | Parcial |

---

## 2. Stack tecnológico

| Componente | Tecnología | Versión | Justificación | ADR referenciado |
|---|---|---|---|---|
| Backend API | FastAPI + asyncio | Python 3.14 | Alto rendimiento, OpenAPI automática, ecosistema ML robusto, compatibilidad con Presidio/spaCy | ADR-003 |
| MCP Server | Módulo FastAPI propio | MCP spec actual | Comparte autenticación, observabilidad y acceso a agentes; protocolo abierto sin lock-in | ADR-003 |
| Frontend | Next.js + TypeScript | Next.js 16.2 | SSR, streaming, self-hosting, compatible con shadcn/ui y Tailwind CSS; React 19; Node.js 24.16.0 | — |
| Base de datos | PostgreSQL | 18.4 | JSONB nativo, Row Level Security (RLS), pgAudit, HA con WAL archiving, TLS | ADR-001 |
| Message broker | Redis | 7.4 | Broker efímero para Dramatiq; cache de Next.js en multi-instancia | ADR-002 |
| Workers | Dramatiq | — | Más simple que Celery para tareas idempotentes sin DAGs complejos; soporta DLQ y backoff | ADR-007 |
| Almacenamiento | MinIO | AGPL / Commercial | S3-compatible, object locking (WORM), erasure coding, Server-Side Encryption (SSE) | ADR-008 |
| Motor de políticas | OPA / Rego | OPA 1.4.0 | Policy-as-code versionado, testeable con `opa test`, hot-reload sin reinicio | ADR-005 |
| Detección NLP/ML | Presidio + spaCy + Transformers | — | Modular, reemplazable via interfaz abstraída `DetectorInterface`, operación offline | ADR-010 |
| Observabilidad | OpenTelemetry + Prometheus | — | Estándar de industria, vendor-neutral, trazas distribuidas + métricas de calidad | ADR-009 |
| Dashboards | Grafana | — | Visualización de métricas Prometheus y error budgets SLO | ADR-009 |
| Orquestación F1-F2 | Docker Compose | v2+ | Despliegue reproducible en single-node con un comando | ADR-006 |
| Orquestación F3+ | Kubernetes | 1.28+ | HPA, PodDisruptionBudget, NetworkPolicy, External Secrets Operator | ADR-006 |
| Proxy reverso | nginx | 1.28 | Terminación TLS, rate limiting, enrutamiento UI/API | — |
| Gestión identidad | Keycloak (OIDC) | 26.2 | SSO/MFA para humanos; OIDC client credentials para agentes MCP | — |
| Secretos (F4+) | OpenBao / KMS | 2.5.4 (fork MPL 2.0, Linux Foundation) | Rotación de claves sin downtime, secretos no estáticos | — |
| Almacenamiento objetos | MinIO | RELEASE.2025-09-07 | S3-compatible, WORM, erasure coding, SSE | ADR-008 |
| Observabilidad — métricas | Prometheus | v3.11.3 | Vendor-neutral, scrape multi-target | ADR-009 |
| Observabilidad — dashboards | Grafana | 13.0.1 | Visualización SLO y error budgets | ADR-009 |

---

## 3. Arquitectura de componentes

### 3.1 Agentes internos

Los agentes internos son la **única fuente de capacidad** del producto. No son integraciones externas. UI y MCP Server los invocan; nunca duplican lógica de negocio.

#### Detector

| Campo | Detalle |
|---|---|
| Responsabilidad | Identificar PII, secretos, credenciales y datos regulados en documentos de texto o binario |
| Inputs | Contenido del documento (texto o base64), nombre de política OPA, versión de política opcional |
| Outputs | Lista de `hallazgos`: span_start, span_end, detector, rule_id, confidence (0.0–1.0), severity, explanation JSON |
| Idempotencia | Dado el mismo documento y la misma versión de política, el Detector produce los mismos hallazgos. El estado del job en PostgreSQL previene re-ejecución si ya existe un resultado para ese `(operation_id, policy_version)` |
| Implementación base | Presidio + spaCy, invocados a través de `DetectorInterface`. Reemplazable sin cambiar el agente |

#### Sanitizador

| Campo | Detalle |
|---|---|
| Responsabilidad | Aplicar redacciones sobre spans detectados; generar `redaction_map` inmutable |
| Inputs | `trace_id` de una operación con hallazgos confirmados, `redaction_type` (mask / remove / replace), token de reemplazo opcional |
| Outputs | Documento sanitizado (texto), `sanitized_artifact_digest` (SHA-256), `redaction_map` con posición, tipo y `policy_version` de cada redacción |
| Idempotencia | El mismo `trace_id` + `redaction_type` produce siempre el mismo documento sanitizado. PostgreSQL almacena el estado `completed` del job, evitando doble ejecución |

#### Clasificador

| Campo | Detalle |
|---|---|
| Responsabilidad | Asignar nivel de sensibilidad al documento y por sección |
| Inputs | Contenido del documento |
| Outputs | `overall_level` (public / internal / confidential / restricted), lista de secciones con nivel y justificación por sección |
| Idempotencia | El mismo documento produce la misma clasificación. Resultado almacenado con `operation_id` como clave de idempotencia |

#### Auditor

| Campo | Detalle |
|---|---|
| Responsabilidad | Registrar toda operación crítica; almacenar artefactos de evidencia en MinIO con WORM |
| Inputs | `operation_id`, artefactos a almacenar (original, sanitizado, exportación de auditoría) |
| Outputs | Registro en tabla `artifacts` con `minio_key`, `digest` SHA-256, `worm_locked = true` |
| Idempotencia | Si el artefacto ya existe en MinIO (mismo `minio_key`), el Auditor verifica digest y no re-escribe. Nunca sobrescribe un objeto WORM |

#### Revisor

| Campo | Detalle |
|---|---|
| Responsabilidad | Escalar a revisión humana cuando `confidence < umbral de clase` o `severity = critical`; funcionar como gate que bloquea el flujo hasta aprobación |
| Inputs | Lista de hallazgos evaluados por OPA, umbrales de la política activa |
| Outputs | `status = escalated` en la operación; notificación a la UI de revisión pendiente |
| Idempotencia | El Revisor solo cambia el estado si la operación está en `pending`. Re-procesar un mensaje con `status = escalated` o posterior es un no-op |

### 3.2 FastAPI Backend

#### Estructura de módulos

```
apps/api/
├── api/
│   ├── v1/
│   │   ├── scan.py          # POST /v1/scan, GET /v1/audit/{trace_id}
│   │   ├── review.py        # GET /v1/review/pending, POST /v1/review/{id}/approve
│   │   └── health.py        # GET /health
│   └── dependencies.py      # auth, rate limiting, DB session
├── mcp/
│   ├── server.py            # POST /v1/mcp/call — dispatch a tools MCP
│   ├── tools/
│   │   ├── scan.py          # safecontext.scan
│   │   ├── sanitize.py      # safecontext.sanitize
│   │   ├── classify.py      # safecontext.classify
│   │   ├── audit.py         # safecontext.audit
│   │   ├── policy_get.py    # safecontext.policy.get
│   │   └── approve.py       # safecontext.approve (v1.1.0)
│   └── auth.py              # Bearer token validation
├── core/
│   ├── agents.py            # Agent Dispatcher — invoca agentes internos
│   ├── policy.py            # Consulta a OPA, cacheo de decisiones
│   └── tracing.py           # OTel span management
├── adapters/
│   ├── redis_adapter.py     # Port & Adapter para Redis (ADR-011)
│   └── minio_adapter.py     # Port & Adapter para MinIO (ADR-011)
├── db/
│   ├── models.py            # SQLAlchemy models: Operation, Finding, Redaction, Artifact, Outbox
│   ├── migrations/          # Alembic migrations
│   └── session.py           # Async DB session factory
└── main.py                  # FastAPI app factory, lifespan hooks
```

#### Outbox pattern

El patrón Outbox garantiza que ningún mensaje llegue a Redis sin estar previamente registrado en PostgreSQL. Esto es el mecanismo central de ADR-001: PostgreSQL es siempre la fuente de verdad.

```
┌────────────────────────────────────────────────────────────┐
│  POST /v1/scan                                             │
│                                                            │
│  1. BEGIN TRANSACTION                                      │
│  2. INSERT INTO operations (status='pending', ...)         │
│  3. INSERT INTO outbox (event_type='scan.requested', ...)  │
│  4. COMMIT                                                 │
│                                ↓                           │
│  Outbox Relay Worker (polling)                             │
│  5. SELECT * FROM outbox WHERE processed = false           │
│  6. actor.send(process_scan, operation_id=...)  → Redis    │
│  7. UPDATE outbox SET processed = true                     │
│                                ↓                           │
│  Worker Dramatiq (Redis)                                   │
│  8. process_scan(operation_id) — ejecuta Detector          │
│  9. Escribe findings en PostgreSQL                         │
│  10. INSERT outbox (event_type='scan.completed')           │
│  11. Relay → encola process_sanitize                       │
└────────────────────────────────────────────────────────────┘
```

Si Redis falla en cualquier momento, el Outbox Relay puede reconstruir la cola leyendo entradas no procesadas en PostgreSQL. No hay pérdida de trabajos.

#### Flujo de scan completo: POST /v1/scan hasta completed

```
1.  Cliente envía POST /v1/scan con {document, policy_name}
2.  api/dependencies.py valida Bearer token → extrae actor_id, actor_type
3.  api/v1/scan.py calcula artifact_digest = SHA-256(document)
4.  core/policy.py consulta OPA: ¿existe política policy_name activa? → policy_version
5.  DB: INSERT operations (status='pending', actor_id, artifact_digest, policy_version)
6.  DB: INSERT outbox (event_type='scan.requested', payload={operation_id})
7.  API retorna 202 Accepted con {trace_id, status='pending'}
8.  Outbox Relay lee outbox → encola process_scan en Redis (Dramatiq)
9.  Worker: process_scan(operation_id)
    a. Carga documento desde operación
    b. Invoca Detector → lista de findings
    c. INSERT findings en PostgreSQL
    d. Consulta OPA: decision(findings) → requires_review, should_block
    e. Si requires_review: UPDATE operations SET status='escalated'
       Si not requires_review: UPDATE operations SET status='sanitize_pending'
    f. INSERT outbox (event_type='scan.evaluated')
10. Outbox Relay → encola process_sanitize (si no escalado)
11. Worker: process_sanitize(operation_id)
    a. Lee findings de PostgreSQL
    b. Aplica redacciones → documento sanitizado
    c. INSERT redactions en PostgreSQL
    d. INSERT outbox (event_type='sanitize.completed')
12. Outbox Relay → encola process_audit
13. Worker: process_audit(operation_id)
    a. Almacena artefactos en MinIO (WORM)
    b. INSERT artifacts en PostgreSQL (minio_key, digest, worm_locked=true)
    c. UPDATE operations SET status='completed', completed_at=now()
14. Cliente puede GET /v1/audit/{trace_id} → evidencia completa
```

### 3.3 MCP Server

El MCP Server es un módulo de FastAPI — no un proceso separado. Expone un único endpoint de dispatch:

```
POST /v1/mcp/call
Authorization: Bearer <token>
Content-Type: application/json

{
  "tool": "safecontext.scan",
  "tool_version": "1.0.0",   // opcional; por defecto la versión más reciente
  "input": { ... }
}
```

#### 6 tools con schemas

| Tool | Versión | Input principal | Output principal |
|---|---|---|---|
| `safecontext.scan` | 1.0.0 | `document` (string), `policy_name` (string) | `trace_id`, `findings[]`, `requires_human_review` |
| `safecontext.sanitize` | 1.0.0 | `trace_id` (UUID), `redaction_type` (mask/remove/replace) | `sanitized_document`, `redaction_map[]` |
| `safecontext.classify` | 1.0.0 | `document` (string) | `overall_level`, `sections[]` con justificación |
| `safecontext.audit` | 1.0.0 | `trace_id` (UUID) | Evidencia completa: operación, findings, redacciones, artefactos, HMAC |
| `safecontext.policy.get` | 1.0.0 | `policy_name` (string), `policy_version` (semver, opcional) | Política OPA activa versionada |
| `safecontext.approve` | 1.1.0 | `finding_id` (UUID), `decision` (approve/reject), `justification` (string) | `approval_trace_id`, `approved_by_agent_id` |

#### Autenticación Bearer token

```
Authorization: Bearer <MCP_AUTH_TOKEN>
X-Client-ID: <client_identifier>   # requerido para rate limiting
```

Respuestas sin token válido: `401 Unauthorized`. El `actor_id` se extrae del JWT claims o del `client_id` del token opaco. Todas las operaciones registran `actor_type = 'mcp_agent'` en PostgreSQL.

#### Versionado

- **1.0.0**: tools base (scan, sanitize, classify, audit, policy.get)
- **1.1.0**: agrega `safecontext.approve` para delegación de aprobación a agentes con permisos explícitos

Los clientes pueden fijar la versión con el campo `tool_version`. Se garantiza compatibilidad N-1: la versión 1.0.0 seguirá siendo funcional durante toda la vida de la 1.1.0.

### 3.4 Workers (Dramatiq)

#### Cadena de procesamiento

```
outbox relay
    │
    ▼
process_scan(operation_id)
    │
    ├── Detector.analyze(document) → findings[]
    ├── OPA.decision(findings) → requires_review, should_block
    ├── Escribe findings en PostgreSQL
    └── INSERT outbox(scan.evaluated)
           │
           ▼ (si not escalated)
process_sanitize(operation_id)
    │
    ├── Sanitizador.redact(document, findings) → sanitized_doc
    ├── INSERT redactions en PostgreSQL
    └── INSERT outbox(sanitize.completed)
           │
           ▼
process_audit(operation_id)
    │
    ├── Auditor.store(original, sanitized) → MinIO WORM
    ├── INSERT artifacts en PostgreSQL
    └── UPDATE operations SET status='completed'
```

#### Idempotencia

Cada worker comienza verificando el `status` de la operación en PostgreSQL antes de ejecutar trabajo:

```python
# Ejemplo: process_scan
@dramatiq.actor(max_retries=5, min_backoff=1000, max_backoff=60000)
def process_scan(operation_id: str):
    op = db.get(Operation, operation_id)
    if op.status != "pending":
        # Mensaje entregado más de una vez — es un no-op
        logger.info("process_scan: idempotent skip", operation_id=operation_id)
        return
    # ... ejecutar análisis
```

Esta verificación garantiza que re-entregar el mismo mensaje produce el mismo estado final sin efectos secundarios.

#### DLQ y retry con backoff exponencial

```python
@dramatiq.actor(
    max_retries=5,
    min_backoff=1_000,   # 1 segundo
    max_backoff=60_000,  # 60 segundos
    queue_name="safecontext",
)
def process_scan(operation_id: str):
    ...
```

Después de 5 reintentos fallidos, el mensaje se mueve a la Dead Letter Queue `safecontext.DQ`. Una alerta Prometheus `DLQDepthHigh` se activa cuando la DLQ tiene mensajes durante más de 5 minutos. El runbook `docs/runbooks/dlq-recovery.md` describe el proceso de recuperación.

#### Outbox relay: PostgreSQL → Redis

El Outbox Relay es un proceso ligero que polling sobre la tabla `outbox` cada 500ms:

```python
while True:
    rows = db.execute("SELECT * FROM outbox WHERE processed = false ORDER BY created_at LIMIT 100")
    for row in rows:
        dispatch_to_dramatiq(row.event_type, row.payload)
        db.execute("UPDATE outbox SET processed = true WHERE id = %s", row.id)
    time.sleep(0.5)
```

En caso de fallo del relay, los mensajes no procesados permanecen en PostgreSQL y se reanudan al reiniciar el relay. Redis nunca es la fuente de verdad.

### 3.5 Policy Engine (OPA/Rego)

OPA se despliega como sidecar o servicio separado, escuchando en `http://opa:8181`.

#### Estructura de la política base

```
policies/
├── base/
│   ├── safecontext.rego        # package safecontext.policy
│   ├── safecontext_test.rego   # OPA unit tests (cobertura >= 80%)
│   └── metadata.json           # {"version": "1.0.0", "entity_classes": [...]}
```

#### Reglas principales

```rego
package safecontext.policy

# Versión de la política — debe coincidir con metadata.json
policy_version := "1.0.0"

# Umbrales por clase de entidad
confidence_thresholds := {
    "EMAIL_ADDRESS": 0.85,
    "PHONE_NUMBER":  0.80,
    "PERSON":        0.85,
    "API_KEY":       0.95,
    "PASSWORD":      0.95,
    "CREDIT_CARD":   0.90,
    "SSN":           0.85,
    "IBAN_CODE":     0.85,
    "IP_ADDRESS":    0.75,
    "MEDICAL_RECORD":0.85,
}

# requires_review: confianza por debajo del umbral o severidad crítica
requires_review(finding) if {
    finding.confidence < confidence_thresholds[finding.entity_type]
}
requires_review(finding) if {
    finding.severity == "critical"
}

# should_block: existe un hallazgo crítico por encima de umbral
should_block(findings) if {
    some f in findings
    f.severity == "critical"
    f.confidence >= confidence_thresholds[f.entity_type]
}

# operation_requires_review: al menos un hallazgo requiere revisión
operation_requires_review(findings) if {
    some f in findings
    requires_review(f)
}

# decision: objeto consolidado de decisión
decision(findings) := {
    "allow":                not should_block(findings),
    "requires_human_review": operation_requires_review(findings),
    "policy_version":        policy_version,
    "findings_count":        count(findings),
    "critical_count":        count([f | f := findings[_]; f.severity == "critical"]),
}
```

#### Hot-reload sin reinicio

OPA soporta recarga de políticas via `PUT /v1/policies/{id}` o reiniciando OPA con el flag `--watch` apuntando al directorio de políticas. En producción, el pipeline de CI/CD actualiza la política en OPA via API sin reiniciar la aplicación ni los workers. El nuevo `policy_version` se registra en la próxima operación que evalúe OPA.

### 3.6 Capa de datos

#### Schema completo de 5 tablas

```sql
-- TABLA: operations
-- Registro central de cada operación de scan/sanitización/clasificación
CREATE TABLE operations (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id       UUID        NOT NULL,           -- correlación del flujo completo
    actor_id       UUID        NOT NULL,           -- ID del humano o agente que inició la op
    actor_type     TEXT        NOT NULL            -- 'human' | 'mcp_agent' | 'pipeline'
                   CHECK (actor_type IN ('human', 'mcp_agent', 'pipeline')),
    document_id    UUID        NOT NULL,           -- referencia lógica al documento
    artifact_digest TEXT       NOT NULL,           -- SHA-256 del documento original (hex 64 chars)
    policy_version TEXT        NOT NULL,           -- semver de la política OPA activa
    status         TEXT        NOT NULL            -- ciclo de vida de la operación
                   CHECK (status IN ('pending','scanning','escalated','sanitize_pending',
                                     'auditing','completed','rejected','failed')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ                    -- NULL hasta completar
);

CREATE INDEX idx_operations_trace_id     ON operations (trace_id);
CREATE INDEX idx_operations_actor_id     ON operations (actor_id);
CREATE INDEX idx_operations_status       ON operations (status);
CREATE INDEX idx_operations_created_at   ON operations (created_at DESC);

ALTER TABLE operations ENABLE ROW LEVEL SECURITY;
-- Política RLS: cada tenant solo ve sus propias operaciones
CREATE POLICY tenant_isolation ON operations
    USING (actor_id = current_setting('app.current_actor_id')::UUID);


-- TABLA: findings
-- Hallazgos individuales detectados dentro de una operación
CREATE TABLE findings (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id  UUID        NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    detector      TEXT        NOT NULL,  -- 'presidio.EMAIL_ADDRESS' | 'regex.API_KEY' | etc.
    rule_id       TEXT        NOT NULL,  -- ID canónico de la regla que generó el hallazgo
    span_start    INT         NOT NULL,  -- posición de inicio (bytes UTF-8) en el documento
    span_end      INT         NOT NULL,  -- posición de fin
    confidence    FLOAT       NOT NULL   -- probabilidad 0.0–1.0
                  CHECK (confidence BETWEEN 0 AND 1),
    severity      TEXT        NOT NULL
                  CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    explanation   JSONB       NOT NULL   -- justificación estructurada: {entity_type, context, ...}
);

CREATE INDEX idx_findings_operation_id  ON findings (operation_id);
CREATE INDEX idx_findings_severity      ON findings (severity);

ALTER TABLE findings ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON findings
    USING (operation_id IN (
        SELECT id FROM operations
        WHERE actor_id = current_setting('app.current_actor_id')::UUID
    ));


-- TABLA: redactions
-- Redacciones aplicadas sobre hallazgos confirmados
CREATE TABLE redactions (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id        UUID        NOT NULL REFERENCES findings(id),
    operation_id      UUID        NOT NULL REFERENCES operations(id),
    redaction_type    TEXT        NOT NULL    -- 'mask' | 'remove' | 'replace'
                      CHECK (redaction_type IN ('mask', 'remove', 'replace')),
    policy_version    TEXT        NOT NULL,  -- versión de política bajo la que se aplicó
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by       UUID,                  -- NULL = aprobación automática por política
    approval_trace_id UUID                   -- trace_id de la operación de aprobación humana
);

CREATE INDEX idx_redactions_operation_id ON redactions (operation_id);
CREATE INDEX idx_redactions_finding_id   ON redactions (finding_id);

ALTER TABLE redactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON redactions
    USING (operation_id IN (
        SELECT id FROM operations
        WHERE actor_id = current_setting('app.current_actor_id')::UUID
    ));


-- TABLA: artifacts
-- Referencias a artefactos almacenados en MinIO
CREATE TABLE artifacts (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id  UUID        NOT NULL REFERENCES operations(id),
    artifact_type TEXT        NOT NULL    -- 'original' | 'sanitized' | 'audit_export'
                  CHECK (artifact_type IN ('original', 'sanitized', 'audit_export')),
    minio_key     TEXT        NOT NULL UNIQUE,  -- ruta en MinIO: bucket/prefix/operation_id/type
    digest        TEXT        NOT NULL,          -- SHA-256 del objeto almacenado en MinIO
    worm_locked   BOOLEAN     NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_artifacts_operation_id ON artifacts (operation_id);

ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON artifacts
    USING (operation_id IN (
        SELECT id FROM operations
        WHERE actor_id = current_setting('app.current_actor_id')::UUID
    ));


-- TABLA: outbox
-- Coordinación transaccional PostgreSQL → Redis (Outbox Pattern)
CREATE TABLE outbox (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type  TEXT        NOT NULL,   -- 'scan.requested' | 'scan.evaluated' | 'sanitize.completed' | ...
    payload     JSONB       NOT NULL,   -- {operation_id, ...}
    processed   BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_outbox_unprocessed ON outbox (created_at ASC) WHERE processed = false;
```

#### RLS: cómo funciona el tenant isolation

Row Level Security de PostgreSQL aplica la política al nivel del motor, antes de que cualquier dato llegue a la aplicación. El backend establece el contexto de actor al inicio de cada sesión:

```sql
SET LOCAL app.current_actor_id = '<actor_uuid>';
```

La política RLS compara `actor_id` con este valor. Cualquier query sobre `operations` — incluyendo JOINs a `findings`, `redactions` y `artifacts` — automáticamente filtra al tenant correcto. No hay código de aplicación que pueda olvidarse de agregar el filtro.

#### pgAudit: qué registra y cómo consultarlo

pgAudit registra todas las operaciones de escritura (`INSERT`, `UPDATE`, `DELETE`) sobre tablas críticas y toda operación `READ` sobre `redactions` y `artifacts`.

```sql
-- Configuración en postgresql.conf
pgaudit.log = 'write, ddl'
pgaudit.log_relation = on
pgaudit.log_catalog = off   -- reducir ruido del sistema

-- Consultar audit log (exportado a tabla estructurada por el collector)
SELECT session_user, object_name, command, object_type, audit_type, statement
FROM pgaudit_log
WHERE object_name IN ('operations', 'findings', 'redactions', 'artifacts')
  AND timestamp > now() - interval '24 hours'
ORDER BY timestamp DESC;
```

Los logs de pgAudit se exportan via OpenTelemetry Collector a un almacén inmutable (MinIO o sistema SIEM del cliente) para cumplimiento regulatorio.

### 3.7 Almacenamiento (MinIO)

#### Estructura de buckets

```
safecontext-artifacts/
├── originals/
│   └── {operation_id}/original.bin       # documento original cifrado
├── sanitized/
│   └── {operation_id}/sanitized.txt      # documento sanitizado
└── audit-exports/
    └── {operation_id}/audit_{trace_id}.json  # evidencia completa exportada

safecontext-policies/
└── base/
    └── v{semver}/safecontext.rego         # snapshots de política por versión
```

#### WORM: por qué y cómo

Object Locking (WORM — Write Once, Read Many) garantiza que los artefactos de evidencia no puedan ser modificados ni eliminados, ni siquiera por el operador del sistema. Esto es un requisito de auditorías regulatorias (GDPR Art. 5(1)(e), HIPAA §164.312).

```bash
# Habilitar en creación del bucket
mc mb --with-lock minio/safecontext-artifacts

# Aplicar retención COMPLIANCE al almacenar un artefacto
mc retention set --default COMPLIANCE "365d" minio/safecontext-artifacts
```

Cualquier intento de `DELETE` o `PUT` sobre un objeto WORM dentro del período de retención retorna `403 MethodNotAllowed`.

#### SSE: cifrado en reposo

Server-Side Encryption con claves gestionadas por MinIO KMS (o Vault en F4+):

```bash
# Configurar SSE en MinIO
mc encrypt set SSE-S3 minio/safecontext-artifacts
mc encrypt set SSE-S3 minio/safecontext-policies
```

Todo objeto se cifra con AES-256 antes de escribirse en disco. Las claves de cifrado se rotan sin downtime desde F4 via KMS.

---

## 4. Flujos principales

### 4.1 Flujo humano (UI)

```
Usuario (browser)          Next.js UI           FastAPI API         Workers (Dramatiq)
      │                        │                     │                      │
      │── POST /upload ────────▶│                     │                      │
      │                        │── POST /v1/scan ────▶│                      │
      │                        │                     │── INSERT operation    │
      │                        │                     │── INSERT outbox       │
      │                        │◀─ 202 {trace_id} ───│                      │
      │◀─ "Procesando..." ──────│                     │                      │
      │                        │                     │── outbox relay ──────▶│
      │                        │                     │              process_scan()
      │                        │                     │              │ Detector.analyze()
      │                        │                     │              │ OPA.decision()
      │                        │                     │              │ INSERT findings
      │                        │                     │              │
      │                        │                     │              ▼ (si escalated)
      │                        │                     │        status = 'escalated'
      │◀── Notificación UI ─────│                     │              │
      │    "Requiere revisión"  │                     │              │
      │                        │                     │              │
      │── Revisar hallazgos ───▶│                     │              │
      │── Aprobar / rechazar ──▶│── POST /v1/review/{id}/approve ──▶│
      │                        │                     │         UPDATE redactions
      │                        │                     │         status = 'sanitize_pending'
      │                        │                     │── outbox relay ──────▶│
      │                        │                     │              process_sanitize()
      │                        │                     │              process_audit()
      │                        │                     │              status = 'completed'
      │                        │                     │                      │
      │── GET /status ─────────▶│── GET /v1/scan/{id}▶│                      │
      │◀─ Documento sanitizado ─│◀────────────────────│                      │
```

### 4.2 Flujo agente MCP

```
Agente LLM (Claude, etc.)       MCP Server          FastAPI Core        Workers
      │                              │                    │                 │
      │── POST /v1/mcp/call ─────────▶│                   │                 │
      │   tool: "safecontext.scan"    │                   │                 │
      │   token: Bearer <mcp_token>   │                   │                 │
      │                              │── validar token    │                 │
      │                              │── extraer actor_id │                 │
      │                              │── POST /v1/scan ──▶│                 │
      │                              │                    │── INSERT op     │
      │                              │                    │── INSERT outbox │
      │                              │                    │── relay ────────▶│
      │                              │                    │         process_scan()
      │                              │                    │         findings → PG
      │                              │◀────── tool_result ─│                 │
      │◀── tool_result {findings} ───│                    │                 │
      │                              │                    │                 │
      │── POST /v1/mcp/call ─────────▶│                   │                 │
      │   tool: "safecontext.sanitize"│                   │                 │
      │   trace_id: <uuid>            │                   │                 │
      │                              │── POST /v1/sanitize▶│                │
      │                              │                    │── process_sanitize()
      │                              │                    │── process_audit()
      │                              │◀── sanitized_doc ───│                │
      │◀── {sanitized_document} ─────│                    │                 │
      │                              │                    │                 │
      │  [Agente usa documento        │                    │                 │
      │   sanitizado con garantía     │                    │                 │
      │   de trazabilidad]            │                    │                 │
```

### 4.3 Flujo pipeline CI/CD

```
git push / PR event
      │
      ▼
GitHub Actions: security-gate.yml
      │
      ├── actions/checkout@v4
      │
      ├── safecontext/action@v1
      │       │
      │       ├── Leer archivos del PR (document-path: ".")
      │       ├── POST /v1/mcp/call (safecontext.scan)
      │       │       │
      │       │       └── Workers: detect → OPA evaluate
      │       │
      │       ├── Evaluar findings vs fail-on-severity
      │       │
      │       ├── Si findings críticos:
      │       │       ├── Escribir PR comment con hallazgos
      │       │       └── exit 1  → Pipeline BLOQUEADO
      │       │
      │       └── Si limpio:
      │               ├── Output: result=pass, trace-id=<uuid>
      │               └── exit 0  → Pipeline CONTINÚA
      │
      ▼ (si pass)
Deploy gate (F3+):
      ├── Verificar firma de imagen (cosign verify)
      ├── Verificar SBOM adjunto
      ├── Deployment protection rule: aprobador humano requerido
      └── Deploy a producción
```

---

## 5. Modelo de datos

El schema SQL completo con comentarios se encuentra en `apps/api/db/migrations/`. A continuación se muestra el schema canónico de referencia:

```sql
-- ============================================================
-- SafeContext — Schema canónico de base de datos
-- PostgreSQL 18.4
-- Todas las tablas con RLS habilitado
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgaudit";     -- audit logging

-- ------------------------------------------------------------
-- operations: registro central de toda operación
-- ------------------------------------------------------------
CREATE TABLE operations (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id       UUID        NOT NULL UNIQUE,
    actor_id       UUID        NOT NULL,
    actor_type     TEXT        NOT NULL CHECK (actor_type IN ('human', 'mcp_agent', 'pipeline')),
    document_id    UUID        NOT NULL,
    artifact_digest TEXT       NOT NULL,    -- SHA-256(documento original), hex 64 chars
    policy_version TEXT        NOT NULL,    -- semver, e.g. '1.0.0'
    status         TEXT        NOT NULL CHECK (
        status IN ('pending','scanning','escalated','sanitize_pending',
                   'auditing','completed','rejected','failed')
    ),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ             -- NULL hasta finalizar
);

CREATE UNIQUE INDEX uix_operations_trace_id ON operations (trace_id);
CREATE INDEX idx_operations_actor_id ON operations (actor_id);
CREATE INDEX idx_operations_status ON operations (status);
CREATE INDEX idx_operations_created_at ON operations (created_at DESC);
ALTER TABLE operations ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- findings: hallazgos individuales por operación
-- ------------------------------------------------------------
CREATE TABLE findings (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id  UUID        NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    detector      TEXT        NOT NULL,    -- e.g. 'presidio.EMAIL_ADDRESS', 'regex.API_KEY'
    rule_id       TEXT        NOT NULL,    -- ID canónico de la regla aplicada
    span_start    INT         NOT NULL,    -- offset byte de inicio
    span_end      INT         NOT NULL,    -- offset byte de fin
    confidence    FLOAT       NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    severity      TEXT        NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    explanation   JSONB       NOT NULL     -- {entity_type, matched_text_hash, context_before, ...}
);

CREATE INDEX idx_findings_operation_id ON findings (operation_id);
CREATE INDEX idx_findings_severity     ON findings (severity);
ALTER TABLE findings ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- redactions: redacciones aplicadas
-- ------------------------------------------------------------
CREATE TABLE redactions (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id        UUID        NOT NULL REFERENCES findings(id),
    operation_id      UUID        NOT NULL REFERENCES operations(id),
    redaction_type    TEXT        NOT NULL CHECK (redaction_type IN ('mask','remove','replace')),
    policy_version    TEXT        NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by       UUID,                  -- UUID del revisor humano; NULL = automático
    approval_trace_id UUID                   -- trace_id de la operación de aprobación
);

CREATE INDEX idx_redactions_operation_id ON redactions (operation_id);
ALTER TABLE redactions ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- artifacts: referencias a artefactos en MinIO
-- ------------------------------------------------------------
CREATE TABLE artifacts (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_id  UUID        NOT NULL REFERENCES operations(id),
    artifact_type TEXT        NOT NULL CHECK (artifact_type IN ('original','sanitized','audit_export')),
    minio_key     TEXT        NOT NULL UNIQUE,    -- e.g. 'safecontext-artifacts/sanitized/<op_id>/sanitized.txt'
    digest        TEXT        NOT NULL,            -- SHA-256 del objeto en MinIO, hex 64 chars
    worm_locked   BOOLEAN     NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_artifacts_operation_id ON artifacts (operation_id);
ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- outbox: coordinación transaccional PG → Redis
-- ------------------------------------------------------------
CREATE TABLE outbox (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type  TEXT        NOT NULL,    -- 'scan.requested' | 'scan.evaluated' | 'sanitize.completed' | 'audit.completed'
    payload     JSONB       NOT NULL,    -- {operation_id, ...}
    processed   BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice parcial: solo registros no procesados para polling eficiente
CREATE INDEX idx_outbox_unprocessed ON outbox (created_at ASC) WHERE processed = false;
```

---

## 6. Decisiones de arquitectura (ADRs resumen)

| ADR | Decisión | Consecuencia principal | Alternativa rechazada |
|---|---|---|---|
| ADR-001 | PostgreSQL como único sistema de registro | Jobs usan Outbox pattern en PG antes de encolar en Redis. Si Redis pierde mensajes, PG permite reencolar | Redis como registro de jobs — riesgo de pérdida de evidencia ante failover |
| ADR-002 | Redis exclusivamente como broker y cache efímero | Redis puede vaciarse sin pérdida de datos de negocio. Next.js multiinstancia requiere custom cache handler | Redis como fuente de verdad de estado |
| ADR-003 | MCP Server implementado como módulo de FastAPI | Versionado de tools gestionado como endpoints REST (/v1/mcp/call). Un solo proceso | MCP Server como proceso separado — duplicación de autenticación y observabilidad |
| ADR-004 | Agentes internos como única fuente de capacidad | Agregar una nueva superficie (CLI, webhook) no requiere reimplementar capacidades | Lógica duplicada en UI y API — divergencia inevitable |
| ADR-005 | OPA/Rego para policy-as-code | Políticas desplegadas por pipeline sin release de la aplicación. Hot-reload en F2 | Reglas hardcodeadas en Python — no versionables, no testeables independientemente |
| ADR-006 | Compose para desarrollo; K8s para Enterprise/HA | Manifiestos K8s generados desde Compose Bridge en F3. No se mantienen dos configs | K8s desde F1 — complejidad innecesaria para MVP |
| ADR-007 | Dramatiq sobre Redis como broker de workers | Workers simples e idempotentes. Umbral de migración a Celery si se requieren DAGs | Celery — más complejo para el modelo de tareas actual |
| ADR-008 | MinIO con WORM + SSE | Artefactos inmutables. Correcciones generan nueva versión, nunca sobrescriben | S3 AWS — incompatible con air-gapped y regulaciones de datos |
| ADR-009 | OpenTelemetry + Prometheus | Trazas distribuidas + métricas de calidad sin vendor lock-in | Datadog/New Relic — SaaS, incompatible con air-gapped |
| ADR-010 | Presidio + spaCy como detectores base, interfaz abstraída | Detector interno no conoce la implementación. Reemplazable sin cambiar agentes | Regex puro — insuficiente para PII en texto no estructurado |
| ADR-011 | Port & Adapter para Redis/MinIO | Redis y MinIO son detalles de infraestructura. Los agentes operan contra interfaces | Acceso directo a Redis/MinIO en la lógica de agentes — acoplamiento fuerte |

---

## 7. Seguridad

### Modelo de identidad

SafeContext distingue tres tipos de actores, cada uno con mecanismo de autenticación propio:

| Actor | Mecanismo | Token lifetime | Observaciones |
|---|---|---|---|
| Humanos (UI) | OIDC + MFA (Keycloak) | JWT corto (15 min) + refresh | SSO empresarial desde F4. MFA obligatorio |
| Agentes MCP externos | OAuth2 client credentials + Bearer token | Configurable, recomendado 1h | Cada agente tiene `client_id` y `actor_id` propios. Rate limit por `client_id` |
| Pipelines CI/CD | OIDC efímero (GitHub/GitLab OIDC) | Por ejecución | Sin secretos estáticos en repositorio desde F3 |
| Comunicación interna API ↔ workers | Token interno de corta vida (F1-F2) → mTLS (F3+) | Por sesión | Zero Trust intra-cluster desde F3 |

### Zero Trust: autenticación inter-componente

```
Request externo
      │
      ▼
nginx (TLS termination + rate limiting)
      │
      ▼
FastAPI (Bearer token validation + RLS context injection)
      │
      ├── → OPA (token interno, red privada)
      ├── → PostgreSQL (TLS + usuario de servicio con permisos mínimos)
      ├── → Redis (AUTH password + red privada, desde F3: TLS)
      └── → MinIO (access key + secret key gestionados por Vault en F4+)

Workers ←→ PostgreSQL: mismo modelo
Workers ←→ MinIO: idem
Workers ←→ Redis: broker solamente, no datos de negocio
```

Cada componente autentica explícitamente. No existe comunicación implícita por confianza de red.

### Port & Adapter pattern para Redis/MinIO (ADR-011)

Los agentes internos nunca importan `redis` ni `minio` directamente. Operan contra interfaces abstractas:

```python
# adapters/interfaces.py
class BrokerPort(Protocol):
    def enqueue(self, queue: str, message: dict) -> None: ...

class ArtifactStorePort(Protocol):
    def store(self, key: str, data: bytes, worm: bool = True) -> str: ...  # retorna digest
    def retrieve(self, key: str) -> bytes: ...

# adapters/redis_adapter.py
class RedisBrokerAdapter(BrokerPort):
    def __init__(self, redis_url: str): ...
    def enqueue(self, queue: str, message: dict) -> None: ...

# adapters/minio_adapter.py
class MinioArtifactAdapter(ArtifactStorePort):
    def __init__(self, endpoint: str, access_key: str, secret_key: str): ...
    def store(self, key: str, data: bytes, worm: bool = True) -> str: ...
```

Este patrón permite reemplazar Redis por RabbitMQ o MinIO por cualquier almacén S3-compatible sin modificar la lógica de los agentes.

### Gestión de secretos por fase

| Fase | Mecanismo | Secretos estáticos |
|---|---|---|
| F1–F2 | Variables de entorno en `.env` (nunca en imagen ni repositorio) | Aceptable en desarrollo; documentado en `.env.example` |
| F3 | OIDC para CI/CD — sin secretos en pipelines. Trivy escanea imágenes | 0 secretos en CI/CD |
| F4 | OpenBao 2.5.4 / KMS. External Secrets Operator en K8s | 0 secretos estáticos en cualquier capa |
| F5 | Vault en modo offline. Rotación de claves documentada para air-gapped | 0 dependencias externas para autenticación |

---

## 8. Observabilidad

### Métricas Prometheus

| Métrica | Tipo | Labels | Descripción |
|---|---|---|---|
| `safecontext_scan_duration_seconds` | Histogram | `status`, `policy_version` | Duración del flujo completo de scan. SLO: p95 < 5s |
| `safecontext_findings_total` | Counter | `entity_class`, `severity`, `detector` | Total de hallazgos detectados por clase y severidad |
| `safecontext_operations_total` | Counter | `status`, `actor_type` | Operaciones por estado y tipo de actor |
| `safecontext_detector_recall` | Gauge | `entity_class` | Recall del detector por clase. Alerta si < 0.95 |
| `safecontext_detector_precision` | Gauge | `entity_class` | Precisión del detector por clase |
| `safecontext_dlq_depth` | Gauge | `queue_name` | Profundidad de Dead Letter Queue. Alerta si > 0 por 5 min |
| `safecontext_outbox_pending` | Gauge | — | Mensajes no procesados en tabla `outbox` |
| `safecontext_api_requests_total` | Counter | `endpoint`, `method`, `status_code` | Total de requests HTTP por endpoint |
| `safecontext_api_latency_seconds` | Histogram | `endpoint`, `method` | Latencia HTTP. SLO: p95 < 500ms (excl. ML) |
| `safecontext_policy_evaluations_total` | Counter | `policy_name`, `policy_version`, `decision` | Evaluaciones OPA por política y decisión |
| `safecontext_minio_upload_duration_seconds` | Histogram | `bucket` | Duración de uploads a MinIO |
| `safecontext_error_budget_consumed` | Gauge | `slo_name` | Porcentaje del error budget mensual consumido |
| `safecontext_human_review_pending` | Gauge | — | Hallazgos escalados esperando revisión humana |
| `safecontext_worker_processing_duration_seconds` | Histogram | `worker_name` | Duración por worker Dramatiq |

### Trazas OTel

OpenTelemetry instrumenta los siguientes puntos del flujo:

```
Span: safecontext.api.scan
  ├── Span: safecontext.policy.consult
  ├── Span: safecontext.db.insert_operation
  └── Span: safecontext.outbox.write

Span: safecontext.worker.process_scan        [propagado desde API via trace_id]
  ├── Span: safecontext.detector.analyze
  │     └── Span: safecontext.presidio.recognize
  ├── Span: safecontext.opa.evaluate
  └── Span: safecontext.db.insert_findings

Span: safecontext.worker.process_sanitize
  ├── Span: safecontext.sanitizer.redact
  └── Span: safecontext.db.insert_redactions

Span: safecontext.worker.process_audit
  ├── Span: safecontext.minio.upload
  └── Span: safecontext.db.insert_artifacts
```

El `trace_id` viaja en el header `X-Trace-ID` de todos los requests y se propaga a los workers via el contexto de Dramatiq. Un único trace_id cubre todo el flujo API → worker → DB → MinIO.

### Dashboards Grafana

| Dashboard | Qué muestra |
|---|---|
| **SafeContext Overview** | Throughput de scans, error rate, latencia p50/p95/p99, operaciones por estado |
| **Detector Quality** | Recall y precisión por clase de entidad, evolución temporal, alertas de degradación |
| **Worker Health** | DLQ depth, retry rate, duración de procesamiento por worker, outbox pending |
| **Security Gate** | Hallazgos por severidad, tasa de bloqueo de pipelines, revisiones humanas pendientes |
| **SLO & Error Budget** | Disponibilidad del scan API (SLO 99.9%), consumo de error budget mensual |
| **Infrastructure** | CPU/memoria/disco de API, workers, PostgreSQL, Redis, MinIO |

### Alertas

| Alerta | Condición | Severidad | Acción |
|---|---|---|---|
| `DLQDepthHigh` | `safecontext_dlq_depth > 0` durante 5 minutos | Critical | Runbook `docs/runbooks/dlq-recovery.md` |
| `SLOErrorBudgetLow` | Error budget < 50% del período | Warning | Investigar degradación de latencia o disponibilidad |
| `DetectorRecallLow` | `safecontext_detector_recall{entity_class="API_KEY"} < 0.95` | Critical | Revisar modelo Presidio, re-evaluar corpus |
| `OutboxStuck` | `safecontext_outbox_pending > 100` durante 10 minutos | Warning | Verificar estado del Outbox Relay y conexión Redis |
| `HumanReviewBacklog` | `safecontext_human_review_pending > 50` | Warning | Notificar a revisores; revisar umbrales de política |
| `WorkerDown` | No hay métricas de worker durante 2 minutos | Critical | Verificar pod/container del worker; consultar logs |

---

## 9. Extensibilidad

### Cómo añadir un detector custom

1. Implementar la interfaz `DetectorInterface`:

```python
# core/interfaces.py
from typing import Protocol, List
from dataclasses import dataclass

@dataclass
class DetectorFinding:
    detector: str          # 'custom.MY_DETECTOR'
    rule_id: str           # 'MY_RULE_001'
    span_start: int
    span_end: int
    confidence: float      # 0.0 – 1.0
    severity: str          # 'low' | 'medium' | 'high' | 'critical'
    explanation: dict      # {entity_type, context, ...}

class DetectorInterface(Protocol):
    def analyze(self, document: str, policy_version: str) -> List[DetectorFinding]:
        ...
```

2. Crear la implementación en `adapters/detectors/`:

```python
# adapters/detectors/my_custom_detector.py
from core.interfaces import DetectorInterface, DetectorFinding

class MyCustomDetector:
    def analyze(self, document: str, policy_version: str) -> list[DetectorFinding]:
        findings = []
        # Tu lógica de detección aquí
        # ...
        return findings
```

3. Registrar en el Agent Dispatcher (`core/agents.py`):

```python
from adapters.detectors.my_custom_detector import MyCustomDetector

DETECTORS = [
    PresidioDetector(),
    MyCustomDetector(),   # añadir aquí
]
```

4. Agregar la clase de entidad y umbrales en la política OPA (`policies/base/safecontext.rego`):

```rego
confidence_thresholds["MY_ENTITY_CLASS"] := 0.90
```

5. Agregar tests en `policies/base/safecontext_test.rego` y ejecutar `opa test policies/ -v`.

No se requiere modificar la API, los workers ni el MCP Server. El nuevo detector es transparente para todas las superficies de consumo.

### Cómo añadir un nuevo tool MCP

1. Crear el handler en `mcp/tools/my_new_tool.py`:

```python
from mcp.models import ToolRequest, ToolResponse

async def handle_my_new_tool(request: ToolRequest) -> ToolResponse:
    # Invocar agentes internos via core/agents.py
    result = await agents.dispatch_my_capability(request.input)
    return ToolResponse(content=result, trace_id=result.trace_id)
```

2. Registrar en el router del MCP Server (`mcp/server.py`):

```python
TOOL_REGISTRY = {
    "safecontext.scan":       (handle_scan,       "1.0.0"),
    # ...
    "safecontext.my_new_tool": (handle_my_new_tool, "1.2.0"),
}
```

3. Definir el schema JSON del tool en `mcp/schemas/my_new_tool.json`.

4. Actualizar `metadata.json` con la nueva versión del MCP Server.

5. Incrementar `tool_version` en el registro y documentar en el changelog de versión.

### Cómo añadir una política OPA nueva

1. Crear el archivo Rego en `policies/<nombre>/`:

```rego
# policies/hipaa/safecontext_hipaa.rego
package safecontext.policy.hipaa

# Umbrales más estrictos para entornos HIPAA
confidence_thresholds["MEDICAL_RECORD"] := 0.75  # más sensible que la base
confidence_thresholds["SSN"] := 0.80
```

2. Crear `metadata.json` con nombre, versión y descripción de la política.

3. Agregar tests en `policies/<nombre>/<nombre>_test.rego`:

```bash
opa test policies/hipaa/ -v
```

4. Cargar la política en OPA via API (sin reinicio):

```bash
curl -X PUT http://opa:8181/v1/policies/hipaa \
  -H "Content-Type: text/plain" \
  --data-binary @policies/hipaa/safecontext_hipaa.rego
```

5. Los clientes pueden ahora usar `policy_name: "hipaa"` en sus requests a `safecontext.scan`.

---

## 10. Glosario técnico

| Término | Definición en SafeContext |
|---|---|
| **artifact_digest** | Hash SHA-256 del artefacto procesado. Inmutable. Parte obligatoria de todo audit trail. Formato: string hexadecimal de 64 caracteres. Identifica inequívocamente el contenido del documento en un momento dado. |
| **trace_id** | Identificador de correlación UUID v4 que une todas las operaciones de un flujo completo (scan → sanitize → audit). Viaja en el header `X-Trace-ID` y en el body de toda respuesta de operación. Permite reconstruir el flujo completo desde un único ID. |
| **policy_version** | Versión semántica (MAJOR.MINOR.PATCH) de la política OPA/Rego activa en el momento de la decisión. Se registra en cada operación, finding y redacción. Permite reproducir exactamente la decisión tomada sobre un documento dado. |
| **hallazgo** | Resultado individual de detección: span afectado (start/end en bytes), detector que lo identificó, rule_id, nivel de confianza (0.0–1.0), severidad y justificación estructurada en JSON. Representa una instancia concreta de dato sensible detectado. |
| **redaction_map** | Mapa inmutable de todas las redacciones aplicadas a un documento: posición (span_start/end), tipo de redacción (mask/remove/replace), justificación y versión de política bajo la que se aplicó. Una vez generado, no puede modificarse; correcciones generan un nuevo trace_id. |
| **gate** | Punto de control que bloquea el flujo hasta que se cumple una condición verificable. No es una advertencia. Tiene resultado binario: pasa o no pasa. Ejemplo: el Revisor es un gate que bloquea la sanitización hasta aprobación humana. |
| **agente interno** | Componente propio de SafeContext que ejecuta una capacidad especializada localmente. Los agentes internos son: Detector, Sanitizador, Clasificador, Auditor, Revisor. No son integraciones externas. Son workers Dramatiq que implementan interfaces bien definidas. |
| **MCP Server** | Superficie de integración que expone los agentes internos como tools consumibles por agentes LLM (Claude, Codex, GitHub Copilot, etc.). Implementado como módulo de FastAPI. Protocolo: Model Context Protocol (MCP). Autenticación: Bearer token. |
| **sistema de registro** | PostgreSQL — única fuente de verdad para decisiones, auditoría, jobs y estado durable. Ningún otro sistema puede ser fuente de verdad. Todo job se registra en PostgreSQL antes de encolarse en Redis. |
| **sistema efímero** | Redis — broker de mensajes Dramatiq y cache transitorio de Next.js. Puede perder datos sin impacto en la integridad del negocio. Nunca fuente de verdad. Su pérdida es recuperable desde el Outbox en PostgreSQL. |

---

*Documento generado a partir de DOC-0 v0.1.0, DOC-2 v0.1.0, DOC-3 v0.1.0 y ADRs cerrados ADR-001 a ADR-011*
*Próxima revisión requerida: inicio de Fase 2*
