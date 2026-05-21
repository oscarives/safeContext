# WORKSPACE.md · SafeContext — Instrucciones para Claude Code
**Versión**: 0.2.0 · **Fecha**: 2026-05-17 · **Actualizado**: 2026-05-21
**Propósito**: instrucciones operacionales para agentes que trabajan en este repositorio.

---

## Estructura del workspace (estado actual)

```
safecontext/
├── README.md                    ← Introducción del proyecto para desarrolladores
├── AGENTS.md                    ← System prompt de Claude Code (leer primero)
├── WORKSPACE.md                 ← Este archivo
├── docker-compose.yml           ← Levantar el stack completo: docker compose up
│
├── docs/
│   ├── ROADMAP.md               ← ⭐ Estado actual del proyecto (leer aquí primero)
│   ├── DOC-0_UNIFIED.md         ← Fuente de verdad: visión, principios, ADRs
│   ├── DOC-1_PRD.md             ← Requisitos funcionales y no funcionales
│   ├── DOC-2_SAD.md             ← Arquitectura, modelo de datos, seguridad
│   ├── DOC-3_SPEC.md            ← Criterios de aceptación por fase (F1–F5 completadas)
│   ├── GLOSSARY.md              ← Glosario canónico de términos
│   ├── SKILLS.md                ← Guías técnicas por dominio (backend, frontend, infra)
│   ├── adr/                     ← 11 Architecture Decision Records (ADR-001 a ADR-011)
│   ├── manuals/                 ← Manuales: usuario, operación, integración, arquitectura
│   ├── runbooks/                ← Runbooks operativos (DR, DLQ, rotación de claves)
│   ├── drills/                  ← Templates de DR drills
│   ├── research/                ← Análisis de madurez externo (deep-research-report.md)
│   └── source/                  ← Documentos fuente (.docx, .pdf)
│
├── apps/
│   ├── api/                     ← FastAPI backend + MCP Server
│   │   ├── api/v1/              ← Endpoints: scan, audit, review, health, operations
│   │   ├── mcp/                 ← MCP Server (tools, schemas, auth)
│   │   ├── core/                ← Auth OIDC, logging, métricas, tracing, ports
│   │   ├── db/                  ← Modelos SQLAlchemy, migraciones Alembic, sesión
│   │   ├── schemas/             ← Pydantic schemas (scan, audit, health)
│   │   ├── adapters/            ← Redis broker adapter (ADR-011)
│   │   └── tests/               ← Tests API, DB, MCP
│   │
│   └── ui/                      ← Next.js 14 frontend (TypeScript + Tailwind)
│       └── src/
│           ├── app/             ← Pages: scan, review, audit, dashboard, login
│           ├── app/api/auth/    ← Route handlers OIDC: session, token, logout
│           ├── app/auth/        ← OIDC callback handler
│           ├── components/      ← SeverityBadge, FindingCard, ConfirmModal, Toast, etc.
│           ├── hooks/           ← useSession
│           ├── lib/             ← session.ts, api-client.ts
│           └── middleware.ts    ← Protección de rutas
│
├── workers/                     ← Dramatiq workers (agentes internos)
│   ├── agents/                  ← detector_agent, sanitizer_agent, classifier_agent,
│   │                               auditor_agent, reviewer_agent
│   ├── core/                    ← DetectorInterface, OPA client, métricas, ports
│   ├── ml/                      ← presidio_detector, model_loader, recall_evaluator
│   ├── adapters/                ← Redis broker, S3 storage (ADR-011)
│   └── tests/                   ← Tests workers, ML, idempotencia, OPA hot-reload
│
├── policies/
│   └── base/                    ← safecontext.rego + safecontext_test.rego
│
├── infra/
│   ├── compose/                 ← Config: Grafana, Keycloak, PostgreSQL, Prometheus,
│   │                               MinIO, Vault, Harbor, Nginx, OTel Collector
│   ├── k8s/                     ← 30 manifiestos Kubernetes
│   ├── github-action/           ← GitHub Action oficial (uses: safecontext/action@v1)
│   └── scripts/                 ← bundle.sh, install-bundle.sh, rollback.sh (air-gapped)
│
└── .github/
    └── workflows/               ← ci.yml, build-sign.yml, ci-selfhosted.yml, deploy.yml
```

---

## Orden de lectura para nuevos agentes

```
1. docs/ROADMAP.md          ← Estado actual, qué está hecho, qué falta
2. docs/DOC-0_UNIFIED.md    ← Por qué existe, principios no negociables
3. AGENTS.md                ← Rol del agente, autonomía, límites
4. docs/SKILLS.md           ← Patrones técnicos por dominio
```

**No implementes nada sin leer ROADMAP.md. Contiene los flags de qué está desarrollado y qué está probado.**

---

## Arrancar el proyecto localmente

```bash
# 1. Variables de entorno
cp .env.example .env

# 2. Stack completo (API + UI + Workers + PG + Redis + MinIO + OTel + Grafana)
docker compose up

# 3. UI en http://localhost:8088
# 4. API en http://localhost:8000/docs
# 5. Grafana en http://localhost:3001
# 6. Keycloak en http://localhost:8080
```

---

## Reglas de trabajo para Claude Code

### Puede hacer sin confirmar
- Leer cualquier archivo
- Escribir código, tests y configuración en rutas existentes
- Ejecutar `ruff check`, `npm test`, `pytest` localmente
- Crear archivos nuevos en rutas definidas en la estructura

### Debe confirmar antes
- Cambios a schemas de base de datos (nuevas migraciones Alembic)
- Cambios a interfaces públicas (endpoints REST, tool schemas MCP)
- Cambios a políticas OPA en `policies/`
- Cambios a workflows de CI/CD en `.github/workflows/`

---

## Estado del proyecto

**F1–F5 completadas. Madurez: 3.5–4/5.**
Para el detalle completo ver `docs/ROADMAP.md`.

Tareas pendientes priorizadas (T1–T10) están documentadas en `docs/ROADMAP.md §7`.

---

*Actualizado: 2026-05-21*
