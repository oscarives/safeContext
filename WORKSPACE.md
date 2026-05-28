# WORKSPACE.md · SafeContext — Instrucciones para Claude Code
**Versión**: 1.0.0 · **Fecha**: 2026-05-25
**Propósito**: instrucciones operacionales para agentes que trabajan en este repositorio.

---

## Estructura del workspace (estado actual)

```
safecontext/
├── README.md                    ← Introducción del proyecto para desarrolladores
├── CLAUDE.md                    ← ⭐ Punto de entrada para agentes (leer primero)
├── AGENTS.md                    ← System prompt operacional de Claude Code
├── WORKSPACE.md                 ← Este archivo
├── docker-compose.yml           ← Levantar el stack completo: docker compose up
│
├── docs/
│   ├── DOC-PRODUCTO.md          ← ⭐ Documento fundacional único (reemplaza DOC-0/1/2/3)
│   ├── ROADMAP.md               ← Estado de implementación, qué está hecho
│   ├── GLOSSARY.md              ← Glosario canónico (~40 términos)
│   ├── SKILLS.md                ← Guías técnicas por dominio (backend, frontend, admin, multi-tenancy)
│   │
│   ├── manuals/
│   │   ├── 01_ARQUITECTURA_TECNICA.md   ← Arquitectura de componentes, stack, flujos
│   │   ├── 02_OPERACION.md              ← Setup, monitoreo, backup, troubleshooting
│   │   ├── 03_USUARIO.md                ← Flujos de usuario por rol
│   │   ├── 04_INTEGRACION_MCP_API.md    ← API REST + MCP tools + OAuth 2.1 + PKCE
│   │   ├── 05_RESUMEN_EJECUTIVO.md      ← Para CTO/CISO/stakeholders
│   │   ├── 06_GUIA_DESARROLLADOR.md     ← Setup dev, patrones, testing, debugging
│   │   ├── 07_ADMIN_CONFIGURACION.md    ← Panel admin: tenants, SIEM, retención, waivers
│   │   ├── 08_ROLES_Y_PERMISOS.md       ← ⭐ RBAC completo: 4 roles, SoD, matrices de permisos
│   │   └── 09_SEGURIDAD_Y_COMPLIANCE.md ← ⭐ Seguridad enterprise: cadena de custodia, GDPR, SIEM
│   │
│   ├── archive/                 ← DOC-0/1/2/3 deprecados (referencia histórica)
│   ├── adr/                     ← 13 Architecture Decision Records (ADR-001 a ADR-013)
│   ├── runbooks/                ← 7 Runbooks operativos (DR, DLQ, rotación de claves)
│   ├── drills/                  ← Templates de DR drills
│   ├── research/                ← Análisis de madurez externo
│   └── source/                  ← Documentos fuente (.docx, .pdf)
│
├── apps/
│   ├── api/                     ← FastAPI backend + MCP Server (Python 3.14)
│   │   ├── api/v1/              ← Endpoints: scan, audit, review, waivers, health, operations
│   │   │   ├── admin_tenants.py ← CRUD tenants (F6)
│   │   │   ├── admin_siem.py    ← SIEM test (F6)
│   │   │   └── admin_retention.py ← GDPR purge + certificados (F6)
│   │   ├── mcp/                 ← MCP Server (tools, schemas, auth OAuth 2.1 + PKCE, scopes)
│   │   ├── core/                ← Auth OIDC, logging, métricas, tracing, ports
│   │   │   ├── auth_oidc.py     ← JWT, RBAC, SoD, rate limiting
│   │   │   ├── chain.py         ← Hash encadenado per-tenant (F6)
│   │   │   ├── vault_transit.py ← Firma digital ECDSA-P256 (F6)
│   │   │   ├── tsa.py           ← Sellado temporal RFC 3161 (F6)
│   │   │   ├── worm.py          ← MinIO Object Lock GOVERNANCE (F6)
│   │   │   ├── retention_gdpr.py ← Purga con certificados firmados (F6)
│   │   │   ├── siem.py          ← CEF/LEEF/JSON a webhook y syslog (F6)
│   │   │   └── quotas.py        ← Rate limiting y quotas per-tenant (F6)
│   │   ├── db/                  ← Modelos SQLAlchemy, 11 migraciones Alembic, sesión
│   │   │   └── migrations/versions/ ← 0001–0011 (base→particionado→waivers→tenants→RLS→chain_hash→tenant_config)
│   │   ├── schemas/             ← Pydantic schemas (scan, audit, sarif, health)
│   │   ├── adapters/            ← Redis broker adapter (ADR-011)
│   │   └── tests/               ← Tests API, DB, MCP, admin (144+ tests)
│   │
│   └── ui/                      ← Next.js 16.2 frontend (TypeScript + Tailwind, React 19, Node 24.16.0)
│       └── src/
│           ├── app/             ← Pages: scan, review, audit, dashboard, login
│           ├── app/admin/       ← Admin Module: layout, tenants, waivers, retention (F6)
│           │   ├── layout.tsx   ← Sidebar + guard rol admin
│           │   ├── tenants/     ← Lista + detalle tenant (3 tabs: General, Políticas, SIEM)
│           │   ├── waivers/     ← Crear/revocar waivers (policy_editor + admin)
│           │   └── retention/   ← Config retención, purga manual, certificados GDPR
│           ├── app/api/auth/    ← Route handlers OIDC: session, token, logout
│           ├── app/auth/        ← OIDC callback handler
│           ├── components/      ← SeverityBadge, FindingCard, ConfirmModal, SimpleConfirmModal,
│           │                       Toast, ToastProvider, EmptyState, Pagination, StatusBadge,
│           │                       LoadingSpinner, NavBar (link Admin condicional)
│           ├── hooks/           ← useSession
│           ├── lib/             ← session.ts, api-client.ts (con métodos admin)
│           └── middleware.ts    ← Protección de rutas
│
├── workers/                     ← Dramatiq workers (agentes internos)
│   ├── agents/                  ← detector_agent, sanitizer_agent, classifier_agent,
│   │                               auditor_agent, reviewer_agent, rescan_agent
│   ├── core/                    ← DetectorInterface, OPA client, métricas, ports
│   ├── ml/                      ← presidio_detector, regex_detector (36 tests), model_loader, recall_evaluator
│   ├── adapters/                ← Redis broker, S3 storage (ADR-011)
│   └── tests/                   ← Tests workers, ML, idempotencia, OPA hot-reload
│
├── policies/
│   └── base/                    ← safecontext.rego + safecontext_test.rego
│                                   (decision, tenant_decision, waivers, confidence_thresholds)
│
├── infra/
│   ├── compose/                 ← Config: Grafana, Keycloak, PostgreSQL, Prometheus,
│   │                               MinIO, OpenBao, Harbor, Nginx, OTel Collector
│   ├── k8s/                     ← Manifiestos Kubernetes
│   ├── github-action/           ← GitHub Action oficial
│   └── scripts/                 ← bundle.sh, install-bundle.sh, rollback.sh (air-gapped)
│
└── .github/
    └── workflows/               ← ci.yml (8 jobs: detect-secrets, lint, test-api, test-ui,
                                     test-opa, test-recall, safecontext-gate, test-e2e)
```

---

## Orden de lectura para nuevos agentes

```
1. CLAUDE.md                               ← Punto de entrada rápido (2 min)
2. docs/ROADMAP.md                         ← Estado actual, qué está hecho
3. docs/DOC-PRODUCTO.md                    ← Por qué existe, requisitos, arquitectura
4. docs/manuals/08_ROLES_Y_PERMISOS.md     ← Los 4 roles y su alcance
5. docs/SKILLS.md                          ← Patrones técnicos por dominio
```

**No implementes nada sin leer ROADMAP.md. Contiene los flags de qué está desarrollado y qué está probado.**

---

## Arrancar el proyecto localmente

```bash
# 1. Variables de entorno
cp .env.example .env

# 2. Stack completo (14 servicios)
docker compose up

# 3. Stack con auth (Keycloak + usuarios de prueba)
docker compose --profile auth up

# 4. Stack full (todo incluyendo monitoring)
docker compose --profile full up

# UI en http://localhost:8088
# API en http://localhost:8000/docs
# Grafana en http://localhost:3001
# Keycloak en http://localhost:8080
```

---

## Estado del proyecto

**F1–F6 completadas. Madurez: 5/5.**

| Métrica | Valor |
|---|---|
| Tests frontend | 112/112 (17 suites) |
| Tests backend | 144+ |
| Tests Docker integración | 59 (7 fases) |
| Migraciones Alembic | 11 |
| ADRs | 13 |
| Runbooks | 7 |
| Servicios Docker | 14 |
| Roles RBAC | 4 (viewer, reviewer, policy_editor, admin) |

Para el detalle completo ver `docs/ROADMAP.md`.

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

*Actualizado: 2026-05-25*
