# DOC-2 · SafeContext — Software Architecture Document (SAD)
**Versión**: 0.1.0 · **Estado**: Draft · **Fecha**: 2026-05-17
**Derivado de**: DOC-0 v0.1.0
**Audiencia**: Arquitecto, Tech Lead, equipo de desarrollo, AppSec

---

## 1. Drivers arquitecturales

Los siguientes drivers son no negociables y condicionan todas las decisiones de diseño:

1. **Explicabilidad total**: ninguna decisión sale sin justificación estructurada.
2. **Auditabilidad inmutable**: toda operación crítica queda registrada en PostgreSQL con trace_id, artifact_digest, actor, policy_version.
3. **Operación offline**: ningún flujo crítico depende de servicios externos.
4. **MCP como superficie de extensión**: los agentes internos son la capacidad; MCP y UI son capas de entrega intercambiables.
5. **Policy-as-code**: las reglas de negocio viven en OPA/Rego, versionadas, testeadas y desplegadas por pipeline.
6. **Supply chain verificable**: toda imagen firmada, con SBOM y provenance desde F3.

---

## 2. Decisiones de arquitectura (ADRs)

### ADR-001 · PostgreSQL como único sistema de registro
- **Contexto**: Redis ofrece mayor velocidad pero usa replicación asíncrona con ventanas de pérdida de datos.
- **Decisión**: PostgreSQL es la única fuente de verdad para decisiones, jobs, auditoría y estado durable. Redis es broker efímero.
- **Consecuencias**: jobs deben usar patrón outbox/event-log en PostgreSQL antes de encolar en Redis. Si Redis pierde mensajes, PostgreSQL permite reencolar.
- **Alternativa rechazada**: Redis como registro de jobs — riesgo de pérdida de evidencia ante partición o failover.

### ADR-002 · Redis exclusivamente como broker y cache efímero
- **Decisión**: Redis no almacena ningún estado que no pueda perderse. Solo broker de Dramatiq y cache de Next.js.
- **Consecuencia**: Next.js en multi-instancia requiere custom cache handler apuntando a Redis. Documentado y configurado desde F1.

### ADR-003 · MCP Server implementado sobre FastAPI
- **Contexto**: MCP requiere un servidor que exponga tools con schemas definidos, autenticación y streaming de respuestas.
- **Decisión**: el MCP Server es un módulo de FastAPI — no un proceso separado. Comparte autenticación, observabilidad y acceso a agentes internos.
- **Consecuencia**: versionado de tools MCP se gestiona como versionado de endpoints REST (/v1/mcp/tools).
- **Riesgo**: si MCP spec evoluciona con breaking changes, el módulo requiere actualización. Mitigación: abstracción de protocolo desde F1.

### ADR-004 · Agentes internos como única fuente de capacidad
- **Decisión**: Detector, Sanitizador, Clasificador, Auditor y Revisor son workers internos. UI y MCP invocan los mismos workers. No existe lógica duplicada por superficie.
- **Consecuencia**: agregar una nueva superficie (CLI, webhook, etc.) no requiere reimplementar capacidades.

### ADR-005 · OPA/Rego para policy-as-code
- **Decisión**: todas las reglas de detección, sanitización y autorización son políticas OPA/Rego.
- **Consecuencia**: las políticas se despliegan por pipeline, no por release de la aplicación. Hot-reload en F2.
- **Alternativa rechazada**: reglas hardcodeadas en Python — no versionables, no auditables, no testeables de forma independiente.

### ADR-006 · Compose para desarrollo; Kubernetes para Enterprise/HA
- **Umbral de migración a K8s**: cuando cualquiera de estas condiciones se cumple: multi-instancia requerida, HPA necesario, multi-tenant, exigencia regulatoria formal de HA.
- **Consecuencia**: manifiestos Kubernetes generados desde Compose Bridge desde F3. No se mantienen dos configuraciones manuales.

### ADR-007 · Dramatiq sobre Redis como broker de workers
- **Decisión**: Dramatiq para workers — más simple que Celery para el modelo de tareas actuales (idempotentes, sin DAGs complejos).
- **Umbral de migración a Celery**: si en F2/F3 se requieren chord/group/chain o scheduling complejo, se reevalúa.
- **Consecuencia**: los workers deben ser idempotentes desde F1 — el broker puede re-entregar mensajes.

### ADR-008 · MinIO con WORM + SSE para artefactos
- **Decisión**: MinIO almacena artefactos de evidencia con object locking (WORM) y cifrado del lado servidor (SSE).
- **Riesgo licencia**: MinIO CE es AGPLv3. Requiere decisión explícita de edición antes de F3.
- **Consecuencia**: los artefactos son inmutables una vez almacenados. Cualquier corrección genera una nueva versión, nunca sobrescribe.

### ADR-009 · OpenTelemetry + Prometheus para observabilidad
- **Decisión**: OTel para trazas distribuidas (API → worker → artefacto). Prometheus para métricas de servicio y calidad. Sin vendor lock-in.
- **Consecuencia**: cada componente instrumentado desde F1. No se instrumenta "después".

### ADR-010 · Presidio + spaCy como detectores base, interfaz abstraída
- **Decisión**: los detectores implementan una interfaz común. Presidio/spaCy son la implementación por defecto, reemplazables por detector custom sin cambiar la capa de agentes.
- **Consecuencia**: el Detector interno no sabe qué librería usa internamente. Esto permite sustituir o combinar detectores sin afectar el flujo.

### ADR-011 · Port & Adapter para Redis (BrokerPort, CachePort) y MinIO (StoragePort)
- **Contexto**: Redis 8 usa licencia tri-license con riesgo legal no resuelto. MinIO CE es AGPLv3 y su repositorio público fue archivado en abril 2026, lo que añade riesgo estratégico de mantenimiento.
- **Decisión**: aislar Redis detrás de `BrokerPort` y `CachePort`; aislar MinIO detrás de `StoragePort` con boto3/S3 API. Toda la lógica de negocio habla con las interfaces, nunca con las implementaciones directamente.
- **Consecuencia**: reemplazar Redis por RabbitMQ = cambiar el adapter + variables de entorno, sin tocar código de negocio. Reemplazar MinIO por cualquier S3-compatible (AIStor, Ceph, AWS S3) = solo cambio de endpoint/credenciales en `.env`.
- **Implementación**: `workers/core/ports.py`, `workers/adapters/redis_broker.py`, `workers/adapters/s3_storage.py`, `apps/api/adapters/redis_broker.py`, `apps/api/core/ports.py`.
- **Alternativa rechazada**: acoplar directamente a Redis y MinIO — el riesgo de licencia y de fin de mantenimiento justifica la abstracción desde F1.

---

## 3. Vista de componentes

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
│  │            OpenTelemetry + Prometheus                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Vista de datos y flujos

### 4.1 Modelo de datos core

```sql
-- Operaciones (sistema de registro)
operations (
  id            UUID PRIMARY KEY,
  trace_id      UUID NOT NULL,
  actor_id      UUID NOT NULL,        -- humano o agente
  actor_type    TEXT NOT NULL,        -- 'human' | 'mcp_agent' | 'pipeline'
  document_id   UUID NOT NULL,
  artifact_digest TEXT NOT NULL,      -- SHA-256 del documento original
  policy_version TEXT NOT NULL,       -- semver de política OPA activa
  status        TEXT NOT NULL,        -- 'pending' | 'completed' | 'escalated' | 'approved' | 'rejected'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at  TIMESTAMPTZ
)

-- Hallazgos
findings (
  id            UUID PRIMARY KEY,
  operation_id  UUID REFERENCES operations(id),
  detector      TEXT NOT NULL,        -- 'presidio.EMAIL' | 'regex.API_KEY' | etc
  rule_id       TEXT NOT NULL,
  span_start    INT NOT NULL,
  span_end      INT NOT NULL,
  confidence    FLOAT NOT NULL,       -- 0.0 - 1.0
  severity      TEXT NOT NULL,        -- 'low' | 'medium' | 'high' | 'critical'
  explanation   JSONB NOT NULL        -- justificación completa estructurada
)

-- Redacciones aplicadas
redactions (
  id            UUID PRIMARY KEY,
  finding_id    UUID REFERENCES findings(id),
  operation_id  UUID REFERENCES operations(id),
  redaction_type TEXT NOT NULL,       -- 'mask' | 'remove' | 'replace'
  policy_version TEXT NOT NULL,
  applied_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_by   UUID,                 -- NULL si automático
  approval_trace_id UUID              -- trace_id de la aprobación humana
)

-- Artefactos de evidencia (referencia a MinIO)
artifacts (
  id            UUID PRIMARY KEY,
  operation_id  UUID REFERENCES operations(id),
  artifact_type TEXT NOT NULL,        -- 'original' | 'sanitized' | 'audit_export'
  minio_key     TEXT NOT NULL,
  digest        TEXT NOT NULL,        -- SHA-256 del artefacto en MinIO
  worm_locked   BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)

-- Outbox para coordinación PostgreSQL → Redis
outbox (
  id            UUID PRIMARY KEY,
  event_type    TEXT NOT NULL,
  payload       JSONB NOT NULL,
  processed     BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

### 4.2 Flujo de scan (happy path)

```
1. Cliente (UI o MCP) envía documento + política seleccionada
2. API crea operation en PostgreSQL (status: pending)
3. API escribe evento en outbox → worker lee de outbox → encola en Redis
4. Worker Detector ejecuta análisis, escribe findings en PostgreSQL
5. OPA evalúa findings contra política → determina severidad y acción
6. Si confianza < umbral OR severidad = critical → Revisor escala (status: escalated)
   → Aprobación humana registrada → operation actualizada (approved_by, approval_trace_id)
7. Worker Sanitizador aplica redacciones, escribe redactions en PostgreSQL
8. Worker Auditor almacena artefactos en MinIO (WORM), actualiza artifacts en PostgreSQL
9. API retorna respuesta con trace_id, findings, redaction_map, artifact_digest
10. OTel registra span completo del flujo
```

### 4.3 Flujo MCP (agente externo)

```
1. Agente LLM invoca safecontext.scan via MCP Server con autenticación OIDC
2. MCP Server valida token, extrae actor_id y actor_type = 'mcp_agent'
3. Flujo idéntico al 4.2 desde paso 2
4. MCP Server retorna tool_result con hallazgos estructurados
5. Audit trail registra actor_id del agente externo — no del usuario humano del agente
```

---

## 5. Plano de seguridad

### 5.1 Modelo de identidad

| Capa | Mecanismo | Observaciones |
|---|---|---|
| Usuarios humanos | OIDC + MFA (F4) | SSO empresarial. JWT con expiración corta. |
| Agentes MCP externos | OAuth2 client credentials + OIDC | Cada agente tiene identidad propia. Rate limit por client_id. |
| Pipelines CI/CD | OIDC efímero (GitHub/GitLab) | Sin secretos estáticos. Token válido por ejecución. |
| Comunicación interna (API ↔ workers) | mTLS o token interno de corta vida | Zero Trust intra-cluster desde F3. |

### 5.2 Autorización

- **RLS en PostgreSQL**: cada tenant/organización solo ve sus propias operations, findings y artifacts.
- **OPA como motor de authz**: las políticas de autorización son Rego, no código Python. Actualizables sin deploy.
- **Roles**: Viewer, Reviewer, PolicyEditor, Admin — segregación de funciones desde F4.

### 5.3 Gestión de secretos

- F1: secretos en variables de entorno (no en código ni imagen).
- F3: OIDC para CI/CD — 0 secretos estáticos en pipelines.
- F4: KMS para rotación de claves de cifrado de MinIO y PostgreSQL.

### 5.4 Supply chain

| Control | Herramienta | Fase |
|---|---|---|
| SBOM por imagen | docker sbom / syft | F3 |
| Firma de imágenes | Cosign + Sigstore | F3 |
| Provenance / SLSA | SLSA GitHub Generator | F3 |
| Escaneo de vulnerabilidades | Trivy en pipeline | F1 |
| Deploy gate | GitHub deployment protection rules | F3 |

---

## 6. Plano de observabilidad

### 6.1 Instrumentación requerida

| Señal | Qué instrumentar | Herramienta |
|---|---|---|
| Trazas | API request → worker → DB → MinIO → response | OpenTelemetry SDK |
| Métricas de servicio | Latencia p50/p95/p99, throughput, error rate por endpoint | Prometheus + OTel |
| Métricas de calidad | Recall por clase de detector, false positive rate, documentos/hora | Prometheus custom metrics |
| Métricas DORA | Deployment frequency, lead time, change fail rate | CI/CD integration |
| Logs estructurados | JSON con trace_id, actor_id, operation_id en cada log | structlog + OTel |

### 6.2 SLOs requeridos (Enterprise)

| SLO | Objetivo | Error budget mensual |
|---|---|---|
| Disponibilidad del scan API | 99.9% | 43 min/mes |
| Latencia p95 scan < 1MB | < 5s | — |
| Latencia p95 API (excl. ML) | < 500ms | — |
| Recall detectores clase crítica | ≥ 0.98 | Alerta si baja de 0.95 |

---

## 7. Modelo de despliegue

### 7.1 F1-F2: Docker Compose (single-node)

```yaml
# Topología mínima
services:
  api:          # FastAPI + MCP Server
  worker:       # Dramatiq workers (Detector, Sanitizador, Clasificador, Auditor, Revisor)
  ui:           # Next.js + reverse proxy nginx
  postgres:     # PostgreSQL con pgAudit
  redis:        # Redis broker/cache
  minio:        # MinIO artefactos
  otel:         # OpenTelemetry Collector
  prometheus:   # Prometheus + Grafana
```

### 7.2 F3-F4: Kubernetes (multi-node / HA)

- HPA en API y workers basado en métricas de cola y CPU.
- PodDisruptionBudget para API y PostgreSQL.
- NetworkPolicy: deny-all por defecto, allow explícito.
- Secrets gestionados por External Secrets Operator + KMS.
- Ingress con TLS terminación y rate limiting.
- PostgreSQL: operador CloudNativePG para HA y WAL archiving.

### 7.3 F5: Air-gapped

- Registry privado (Harbor o similar) con todas las imágenes firmadas.
- Runners/agentes CI/CD self-hosted sin acceso a internet.
- Modelos NLP/ML empaquetados en imagen o volumen.
- Bundle de actualización con proceso documentado y probado.
- DR drill completo en entorno sin internet antes de certificar F5.

---

## 8. Riesgos arquitecturales

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Redis usado como registro accidentalmente | Alta sin disciplina | Alto — pérdida de evidencia | Outbox pattern en PostgreSQL desde F1. Prohibición documentada en ADR-001. |
| Next.js cache inconsistente en multi-instancia | Alta si no se configura | Medio — UI errática | Custom cache handler con Redis desde F1. Test de consistencia en F2. |
| Licencia Redis 8 tri-license incompatible | Media | Alto — bloqueo legal | Revisión legal antes de F2. Plan B: RabbitMQ como broker. |
| Licencia MinIO CE AGPLv3 incompatible | Media | Alto — bloqueo legal | Decisión explícita de edición antes de F3. |
| MCP spec con breaking changes | Baja a media | Medio | Abstracción de protocolo desde F1. Versionado de tools desde F2. |
| Detector con recall < umbral en producción | Media | Alto — fuga de datos no detectada | Evaluación continua con corpus etiquetado desde F1. Alertas automáticas. |
| Python 3.12 EOL | Baja (2028) | Medio | Plan de migración a 3.13+ en roadmap F3-F4. |
| Deuda de UI por shadcn sin sistema de diseño | Alta | Bajo-Medio | ADRs de componentes y tokens de diseño desde F1. |

---

*Derivado de DOC-0 v0.1.0*
*Actualizado: 2026-05-21 — añadido ADR-011*
*Para estado actual de implementación ver `docs/ROADMAP.md`*
