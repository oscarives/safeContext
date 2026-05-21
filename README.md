# SafeContext

**Plataforma de gobierno de contexto para pipelines de IA**

SafeContext garantiza que ningún documento sensible llegue a un modelo de IA sin haber pasado por un proceso verificable, auditable y explicable de detección, sanitización y aprobación humana.

---

## El problema

Las organizaciones que usan Claude, Copilot, Codex o cualquier LLM para procesar documentos internos no tienen forma de:

- Saber qué datos sensibles están en el contexto que envían al modelo
- Demostrarlo ante un auditor de cumplimiento normativo (GDPR, HIPAA, SOC2)
- Hacerlo de forma automática sin depender de servicios cloud externos

## La solución

SafeContext actúa como **intermediario de seguridad** entre tus documentos y los modelos de IA:

```
Documento → SafeContext → Detección + Sanitización + Aprobación → Modelo de IA
                                         ↓
                              Audit trail inmutable y verificable
```

Tres diferenciales clave:

1. **MCP Server nativo** — cualquier agente LLM compatible (Claude, Copilot, Codex) lo consume como herramienta sin lock-in
2. **Opera completamente offline** — válido en entornos air-gapped, salud, defensa, finanzas
3. **Toda decisión es explicable y auditable** — defendible ante GDPR, HIPAA, SOC2

---

## Inicio rápido

```bash
# 1. Copiar variables de entorno
cp .env.example .env

# 2. Levantar el stack completo
docker compose up

# 3. Acceder a la UI
open http://localhost:8088

# 4. API disponible en
open http://localhost:8000/docs
```

**Requiere**: Docker Desktop 24+ y 8 GB RAM disponibles.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                      SafeContext Core                       │
│   Detector · Sanitizador · Clasificador · Auditor · Revisor │
├──────────────────────┬──────────────────────────────────────┤
│    UI Web            │         MCP Server                   │
│    (Next.js)         │    (protocolo MCP estándar)          │
│                      │  Claude / Copilot / GitHub Actions   │
└──────────────────────┴──────────────────────────────────────┘
         ↓                              ↓
   PostgreSQL (registro)    Redis (broker efímero)    MinIO (artefactos)
```

## Estructura del repositorio

```
safecontext/
├── apps/
│   ├── api/          FastAPI backend + MCP Server
│   └── ui/           Next.js frontend (OIDC, review, audit, scan)
├── workers/          Dramatiq workers (Detector, Sanitizador, Clasificador, Auditor, Revisor)
├── policies/         Políticas OPA/Rego (policy-as-code, versionadas)
├── infra/
│   ├── compose/      Configuración Docker Compose (Grafana, Keycloak, PostgreSQL, etc.)
│   ├── k8s/          Manifiestos Kubernetes (30 recursos, NetworkPolicy, HPA)
│   └── scripts/      Scripts de bundle, instalación y rollback offline
├── docs/
│   ├── ROADMAP.md    ← Estado actual del proyecto (leer aquí primero)
│   ├── DOC-0_UNIFIED.md   Fuente de verdad: visión, principios, ADRs
│   ├── adr/          11 Architecture Decision Records
│   ├── manuals/      Manuales de usuario, operación e integración
│   └── runbooks/     Runbooks operativos (DR, DLQ, rotación de claves)
└── .github/
    └── workflows/    CI/CD (lint, tests, SBOM, firma Cosign, deploy gate)
```

---

## Flujos principales

**Desde la UI:**
```
Pegar documento → Scan → Findings con spans resaltados →
Revisión humana (si crítico) → Audit trail exportable con HMAC
```

**Desde un agente LLM (MCP):**
```python
# El agente verifica el documento antes de procesarlo
result = await mcp_client.call_tool("safecontext.scan", {
    "document": content,
    "policy_name": "default"
})
# → findings con confidence, severity, rule_id, trace_id
```

**Desde CI/CD:**
```yaml
- uses: safecontext/action@v1
  with:
    api-url: ${{ vars.SAFECONTEXT_URL }}
    fail-on-severity: critical
```

---

## Estado del proyecto

**Madurez**: 3.5–4 / 5 · Fases F1–F5 completadas

| Dimensión | Estado |
|---|---|
| Backend API + Workers | ✅ |
| Frontend UI (OIDC, scan, review, audit) | ✅ |
| MCP Server | ✅ |
| Supply chain (SBOM, Cosign, SLSA) | ✅ |
| Kubernetes + Observabilidad | ✅ |
| Offline / Air-gapped | ✅ |

Para el estado detallado y las tareas pendientes ver [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Estado actual, fases, tareas pendientes |
| [`docs/DOC-0_UNIFIED.md`](docs/DOC-0_UNIFIED.md) | Visión, principios no negociables, ADRs |
| [`docs/manuals/03_USUARIO.md`](docs/manuals/03_USUARIO.md) | Manual de usuario |
| [`docs/manuals/04_INTEGRACION_MCP_API.md`](docs/manuals/04_INTEGRACION_MCP_API.md) | Integración MCP y API |
| [`docs/manuals/06_GUIA_DESARROLLADOR.md`](docs/manuals/06_GUIA_DESARROLLADOR.md) | Guía del desarrollador |
| [`docs/runbooks/`](docs/runbooks/) | Runbooks operativos |

---

## Tecnologías

Python 3.12 · FastAPI · PostgreSQL · Redis · MinIO · OPA/Rego · Next.js 14 · TypeScript · Keycloak · HashiCorp Vault · OpenTelemetry · Prometheus · Grafana · Docker · Kubernetes · Cosign · Harbor
