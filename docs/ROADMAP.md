# SafeContext — ROADMAP
**Versión**: 1.0.0 · **Última actualización**: 2026-05-21
**Audiencia**: Claude Code, Tech Lead, nuevos colaboradores, agentes de desarrollo
**Autoridad**: Este documento refleja el estado real del proyecto. Ante contradicción con DOC-3_SPEC.md, este prevalece en cuanto a estado de implementación.

---

## Instrucción para agentes

Lee este documento completo antes de tocar cualquier archivo. Contiene:
- Por qué existe el proyecto y qué problema resuelve
- Qué está hecho, qué está probado, qué falta
- Las tareas pendientes priorizadas con criterios de aceptación

**No asumas que algo está implementado porque suena lógico. Consulta los flags.**
**No implementes algo que ya existe. Consulta los flags antes de crear código nuevo.**

---

## 1. Por qué existe SafeContext

### Origen

SafeContext nace de un problema estructural en la adopción de IA generativa en entornos corporativos: **no existe un mecanismo estándar, auditable y enterprise-grade para garantizar que el contexto que llega a un modelo de IA no contiene datos sensibles**.

Las organizaciones que usan Claude, Copilot, Codex o cualquier LLM para procesar documentos internos no tienen forma de:
1. Saber qué datos sensibles están en el contexto que envían al modelo
2. Demostrarlo ante un auditor de cumplimiento normativo
3. Hacerlo de forma automática, reproducible y sin depender de servicios cloud externos

### Qué no es SafeContext

- **No es un escáner de secretos** (detect-secrets, truffleHog) — esos detectan credenciales en código, no en documentos de negocio ni en contextos de IA
- **No es un DLP corporativo** (Symantec, Forcepoint) — esos no tienen integración nativa con pipelines de IA ni con el protocolo MCP
- **No es un sanitizador mágico** — los motores de PII no garantizan detectar toda la información sensible (Presidio lo documenta explícitamente). SafeContext es una **plataforma de control y gobernanza**, no un sistema de detección perfecta

### Qué es SafeContext

Una **plataforma de gobierno de contexto para pipelines de IA**, con tres diferenciales:

1. **Expone capacidades como MCP Server** — cualquier agente LLM compatible (Claude, Codex, Copilot, agente custom) consume SafeContext como herramienta nativa sin lock-in
2. **Opera completamente offline** — viable en entornos air-gapped y sectores regulados (salud, defensa, finanzas)
3. **Toda decisión es explicable, auditable e inmutable** — defendible ante GDPR, HIPAA, SOC2

---

## 2. Problema que resuelve

| Problema | Consecuencia sin SafeContext |
|---|---|
| Documentos con PII, secretos o datos confidenciales ingresan a modelos de IA | Fuga de datos no detectable, violación GDPR/HIPAA |
| Los pipelines de CI/CD no verifican qué contexto envían a herramientas de IA | Exposición de credenciales, configuraciones internas, datos de clientes |
| Las decisiones de sanitización son opacas | No auditables, no defendibles ante compliance |
| Los agentes LLM no pueden verificar la seguridad del contexto que consumen | El agente opera sobre datos no validados |
| Las soluciones existentes envían datos a SaaS externos | Incompatible con entornos regulados y air-gapped |

---

## 3. Marco completo de la solución

### 3.1 Arquitectura en dos capas

```
┌─────────────────────────────────────────────────────────────┐
│                      SafeContext Core                       │
│                                                             │
│   Agentes internos (locales, especializados)                │
│   Detector · Sanitizador · Clasificador · Auditor · Revisor │
│                                                             │
├──────────────────────┬──────────────────────────────────────┤
│    UI Web            │         MCP Server                   │
│    (Next.js + TS)    │    (protocolo MCP estándar)          │
│                      │                                      │
│  Consume agentes     │  Expone agentes como tools a:        │
│  internos para       │  · Claude / Codex / cualquier LLM   │
│  operación humana    │  · GitHub Actions / GitLab CI        │
│                      │  · Agentes custom del cliente        │
└──────────────────────┴──────────────────────────────────────┘
```

**Principio invariante**: la UI y el MCP Server son capas de entrega sin lógica de negocio. Los agentes internos son la única fuente de capacidad.

### 3.2 Agentes internos

| Agente | Responsabilidad | Autonomía |
|---|---|---|
| **Detector** | Identificar PII, secretos, datos sensibles | Alta — opera sin intervención en casos claros |
| **Sanitizador** | Redactar, enmascarar o eliminar contenido detectado | Alta — ejecuta según política versionada |
| **Clasificador** | Asignar nivel de sensibilidad al documento | Alta |
| **Auditor** | Registrar cada decisión con trace_id, policy_version, artifact_digest, actor | Total — nunca omite registro |
| **Revisor** | Escalar a revisión humana cuando confianza < umbral | Gate — bloquea hasta aprobación |

### 3.3 Superficies de consumo

| Superficie | Endpoint / Herramienta | Autenticación |
|---|---|---|
| UI Web | `http://[host]:8088` | OIDC + MFA (Keycloak) |
| MCP Server | `/v1/mcp/tools/*` | Bearer token (→ OAuth 2.1/PKCE en T8) |
| REST API | `/v1/scan`, `/v1/audit`, `/v1/review`, `/v1/operations` | Bearer token |
| GitHub Action | `uses: safecontext/action@v1` | OIDC efímero |

### 3.4 Flujos principales

**Flujo humano (UI)**:
```
Usuario pega documento → /scan → workers detectan → si crítico: escala a revisión →
Reviewer aprueba/rechaza con justificación → audit trail inmutable → documento sanitizado
```

**Flujo agente externo (MCP)**:
```
Agente invoca safecontext.scan → detector analiza →
hallazgos con explicación completa → agente invoca safecontext.sanitize →
documento sanitizado + redaction_map + trazabilidad
```

**Flujo pipeline CI/CD**:
```
Push/PR → GitHub Action → safecontext.scan →
si hallazgos críticos: pipeline bloqueado + reporte en PR →
si limpio: pipeline continúa con evidencia de escaneo adjunta
```

### 3.5 Principios no negociables

1. **PostgreSQL es el único sistema de registro** — Redis es efímero, nunca fuente de verdad
2. **Determinismo primero** — reglas determinísticas para secretos y credenciales, ML complementa
3. **Toda decisión es explicable** — rule_id + detector + confianza + policy_version sin excepciones
4. **Toda operación crítica genera audit trail** — trace_id + artifact_digest + actor + timestamp
5. **El producto opera sin internet** — ningún flujo crítico depende de SaaS externo
6. **Las políticas son código** — versionadas, testeadas, desplegadas por pipeline
7. **La revisión humana es un gate** — para hallazgos críticos el flujo se bloquea hasta aprobación
8. **Los originales nunca se modifican** — toda redacción genera artefacto nuevo; el original se preserva

### 3.6 Stack tecnológico

| Componente | Tecnología | Versión actual | Nota |
|---|---|---|---|
| Backend | FastAPI + Python | 3.12.x | Upgrade a 3.13+ planificado |
| Frontend | Next.js + TypeScript | 14.2.3 / TS 5 | Upgrade a 15+ planificado |
| Base de datos | PostgreSQL | 15 (CI), 17+ recomendado | JSONB + RLS + pgAudit |
| Cola/Workers | Redis + Dramatiq | Redis 7 | Broker efímero únicamente |
| Almacenamiento | MinIO (StoragePort abstraction) | CE AGPLv3 | ADR-011: swap = solo `.env` |
| Motor de políticas | OPA / Rego | 0.60+ | Policy-as-code versionado |
| Observabilidad | OTel + Prometheus + Grafana | — | Vendor-neutral |
| Auth | Keycloak | Self-hosted | OIDC + MFA |
| KMS | HashiCorp Vault | Self-hosted | Rotación de claves |
| Registry | Harbor | Self-hosted | Air-gapped ready |
| Orquestación | Docker Compose → Kubernetes | — | Compose F1-F2; K8s F3+ |
| NLP/PII | Presidio + spaCy en_core_web_lg | 2.2.x | Interfaz abstraída (ADR-010) |

---

## 4. Modelo de madurez

| Nivel | Nombre | Criterio |
|---|---|---|
| 0 | Idea | Visión sin arquitectura |
| 1 | Diseño conceptual | Módulos definidos, stack elegido |
| 2 | Diseño controlado | ADRs, bounded contexts, roadmap, criterios de aceptación |
| 3 | Plataforma funcional | Core determinístico, UI, políticas, DevSecOps mínimo |
| 4 | Piloto enterprise | Auditoría completa, OIDC, observabilidad, MCP seguro, offline |
| **5** | **Enterprise regulado** | Multi-tenant, evidencias firmadas, hardening, compliance repetible |

**Estado actual: 3.5–4 / 5**
El informe externo estimó 1–2/5 en mayo 2026. Las fases F1–F5 del plan original están completadas.
Los gaps que quedan para cerrar el 4/5 limpio son las tareas T1–T10 del replanteo (ver §7).

---

## 5. Fases del plan original

Convención de flags:
- `✅ desarrollado` = código en producción en el repo
- `✅ tests` = hay tests automatizados que verifican el criterio
- `⚠️` = implementado pero con deuda técnica conocida
- `❌` = no implementado

---

### F1 · Base segura ✅ COMPLETADA

**Objetivo**: estructura técnica correcta, observabilidad básica, pipeline gate funcional.

| Entregable | Descripción | Desarrollado | Tests |
|---|---|---|---|
| E1.1 · Repositorio | Monorepo, .gitignore, pre-commit hooks, ADRs, glosario | ✅ | ✅ |
| E1.2 · Esquema BD | 5 tablas con RLS, pgAudit, índices en trace_id/actor_id | ✅ | ✅ `tests/db/test_schema.py` |
| E1.3 · Backend API | `POST /v1/scan`, trace_id en todas las respuestas, `/health`, Dockerfiles | ✅ | ✅ `tests/api/test_scan.py` |
| E1.4 · MCP Server | scan, sanitize, classify tools; auth 401; audit trail por actor | ✅ | ✅ `tests/mcp/test_mcp_tools.py` |
| E1.5 · Workers | Detector, Sanitizador, Clasificador, Auditor, Revisor; idempotentes; outbox; DLQ | ✅ | ✅ `tests/workers/test_idempotency.py` |
| E1.6 · OPA/Rego | Política base, umbrales, severidades, tests con cobertura ≥ 80% | ✅ | ✅ `policies/base/safecontext_test.rego` |
| E1.7 · Observabilidad | OTel SDK, trace_id end-to-end, Prometheus, Grafana dashboard | ✅ | ✅ |
| E1.8 · Pipeline gate | GitHub Action, pass/block, reporte en PR | ✅ | ✅ |
| E1.9 · Docker Compose | Stack completo (API, UI, workers, PG, Redis, MinIO, OTel, Grafana) | ✅ | ✅ |

**Gate F1 → F2**: ✅ todos los criterios verificados

---

### F2 · Producto endurecido ✅ COMPLETADA

**Objetivo**: operación repetible, backup/restore probado, auditoría detallada, jobs resilientes.

| Entregable | Descripción | Desarrollado | Tests |
|---|---|---|---|
| E2.1 · Auditoría | pgAudit completo, `GET /v1/audit/{trace_id}` con HMAC-SHA256, retención | ✅ | ✅ `tests/api/test_audit.py` |
| E2.2 · MinIO WORM | Object locking, SSE, versioning, retención por bucket | ✅ | ✅ |
| E2.3 · Resiliencia workers | Retries + backoff, DLQ con alerta, OPA hot-reload, graceful shutdown | ✅ | ✅ `tests/workers/test_opa_hot_reload.py` |
| E2.4 · Backup/DR | Backup diario PG + MinIO, restore probado < 1h, runbook documentado | ✅ | ✅ |
| E2.5 · Cache distribuido | Next.js custom cache handler → Redis, test de consistencia multiinstancia | ✅ | ✅ |
| E2.6 · Revisión humana UI | Página `/review`, ConfirmModal (≥20 chars justificación), SoD, toasts | ✅ | ✅ `src/app/__tests__/review.test.tsx` |
| E2.7 · Tools MCP | `safecontext.audit`, `safecontext.policy.get` | ✅ | ✅ `tests/mcp/test_mcp_versioning.py` |

**Gate F2 → F3**: ✅ todos los criterios verificados

---

### F3 · Supply chain y gobierno ✅ COMPLETADA

**Objetivo**: cadena de suministro verificable, 0 secretos estáticos, deploy gate activo.

| Entregable | Descripción | Desarrollado | Tests |
|---|---|---|---|
| E3.1 · OIDC y secretos | GitHub Actions con OIDC, 0 secretos estáticos, auth interna API↔workers | ✅ | ✅ |
| E3.2 · SBOM y firma | SBOM por imagen (Syft), Cosign keyless, SLSA provenance, deploy gate | ✅ | ✅ `.github/workflows/build-sign.yml` |
| E3.3 · Deploy gate | Protection rules, excepciones auditadas, Trivy en pipeline | ✅ | ✅ |
| E3.4 · Kubernetes | 30 manifiestos K8s, NetworkPolicy deny-all, HPA, PodDisruptionBudget | ✅ | ✅ |

**Gate F3 → F4**: ✅ todos los criterios verificados

---

### F4 · Enterprise operativo ✅ COMPLETADA

**Objetivo**: SSO/MFA, SLOs con error budget, DR verificado, segregación de funciones.

| Entregable | Descripción | Desarrollado | Tests |
|---|---|---|---|
| E4.1 · Identidad y acceso | Keycloak SSO/MFA, roles Viewer/Reviewer/PolicyEditor/Admin, SoD, rate limiting | ✅ | ✅ |
| E4.2 · KMS | HashiCorp Vault integrado, rotación de claves MinIO sin downtime | ✅ | ✅ |
| E4.3 · SLOs | 99.9% disponibilidad, p95 < 5s, error budget dashboard, alertas | ✅ | ✅ |
| E4.4 · DR verificado | RTO < 15 min en drill, RPO < 5 min, drill trimestral en calendario | ✅ | ✅ |
| E4.5 · Versionado MCP | tool_version en requests, backward compat N-1 | ✅ | ✅ `tests/mcp/test_mcp_versioning.py` |
| E4.6 · safecontext.approve | Aprobación delegada a agentes con identidad registrada | ✅ | ✅ |

**Gate F4 → F5**: ✅ todos los criterios verificados

---

### F5 · Desconectado regulado ✅ COMPLETADA

**Objetivo**: instalación, operación, actualización y rollback completos sin internet.

| Entregable | Descripción | Desarrollado | Tests |
|---|---|---|---|
| E5.1 · Harbor | Registry privado, cosign verify contra registry local | ✅ | ✅ |
| E5.2 · CI self-hosted | Runners sin acceso a internet, OIDC en entorno aislado | ✅ | ✅ `.github/workflows/ci-selfhosted.yml` |
| E5.3 · Modelos offline | Presidio + spaCy empaquetados en imagen, actualización sin internet | ✅ | ✅ `tests/ml/test_offline_models.py` |
| E5.4 · Bundle actualización | Script de bundle, upgrade N→N+1 sin internet, rollback probado | ✅ | ✅ |
| E5.5 · DR air-gapped | Drill completo en entorno sin internet, RTO < 15 min verificado | ✅ | ✅ |

**Gate F5 (Enterprise air-gapped)**: ✅ todos los criterios verificados

---

## 6. Frontend (completado en paralelo con F2)

La UI fue replanteda y completada como proyecto independiente después de detectar que el frontend inicial era un esqueleto sin funcionalidad.

| Entregable | Descripción | Desarrollado | Tests |
|---|---|---|---|
| Auth OIDC | Callback Keycloak, cookie httpOnly, middleware de rutas, `useSession` | ✅ | ✅ `src/middleware.test.ts` |
| Cliente HTTP | Bearer token automático, manejo 401/403, caché de token | ✅ | ✅ |
| Componentes | SeverityBadge, StatusBadge, FindingCard, DocumentViewer, ConfirmModal, Toast, EmptyState, Pagination | ✅ | ✅ `src/components/__tests__/` |
| Página `/scan` | Formulario, polling async, spans resaltados, link a revisión | ✅ | — |
| Página `/review` | ConfirmModal (≥20 chars), SoD display, filtro por trace_id | ✅ | ✅ `src/app/__tests__/review.test.tsx` |
| Página `/audit` | Findings expandibles, redacciones, HMAC display, descarga correcta | ✅ | ✅ `src/app/__tests__/audit.test.tsx` |
| Página `/dashboard` | Health fix, stats con fallback, actividad reciente, nav con rol | ✅ | — |
| NavBar | Nombre de usuario, rol, logout, todos los items | ✅ | — |

**Suite de tests UI**: 43/43 pasando (`npm test`)

---

## 7. Plan de mejora — Replanteo del informe de madurez

Estas tareas surgieron del análisis externo (`docs/research/deep-research-report.md`) que evaluó el proyecto contra estándares enterprise-grade. Son los gaps que quedan para alcanzar el nivel 4/5 limpio.

**Ninguna bloquea el funcionamiento actual. Todas elevan el nivel para piloto enterprise real.**

---

### Bloque A — Calidad de producto (mayor impacto, menor esfuerzo)

| ID | Tarea | Descripción | Criterio de aceptación | Esfuerzo | Desarrollado | Tests |
|---|---|---|---|---|---|---|
| **T1** | SARIF output | Exportar findings en formato SARIF 2.1 además de JSON propio. SARIF es el estándar que consume GitHub Advanced Security, SonarQube, etc. Sin esto, la integración en pipelines enterprise requiere trabajo extra del cliente. | `GET /v1/audit/{trace_id}?format=sarif` retorna SARIF válido contra schema oficial. `opa test` y CI verifica esquema. | 2 días | ❌ | ❌ |
| **T2** | actor_id real desde JWT | Hoy `actor_id = 00000000-0000-0000-0000-000000000001` en todas las operaciones. El audit trail no es trazable por usuario. | `POST /v1/scan` extrae `sub` del JWT Bearer y lo guarda como `actor_id`. Operaciones MCP guardan `client_id` del token. Test: operación crea registro con actor_id ≠ sentinel. | 1 día | ❌ | ❌ |
| **T3** | Rescan post-sanitización | Después de sanitizar, el documento redactado no se vuelve a analizar. Si quedan fugas, no se detectan. El informe lo marca como obligatorio. | Worker sanitizador invoca detector sobre el documento redactado. Si hay findings residuales, escala de nuevo. Test con documento que tiene PII en posición que podría quedar parcialmente redactada. | 2 días | ❌ | ❌ |

---

### Bloque B — Seguridad de datos (crítico para compliance real)

| ID | Tarea | Descripción | Criterio de aceptación | Esfuerzo | Desarrollado | Tests |
|---|---|---|---|---|---|---|
| **T4** | Capa de reglas determinísticas | Hoy Presidio (ML) es el único motor de detección. El informe dice: "determinismo primero — la IA complementa, no reemplaza". Si el modelo no detecta un patrón nuevo (nuevo formato de API key, credencial custom), no hay net de seguridad. | Implementar `RegexDetector` que corra ANTES de Presidio con reglas para: connection strings, UUIDs en asignaciones `secret=`, tokens JWT, patrones de tarjetas en formatos no estándar. Mismo `DetectorInterface`. Test con patrones que Presidio no detecta. | 5 días | ❌ | ❌ |
| **T6** | Golden corpus formal con métricas | Existe `corpus.json` con 30 samples pero no hay pipeline de evaluación en CI. El informe exige recall ≥ 95% en PII/PHI y ≥ 99% en secretos críticos, medido y documentado. Sin esto no se puede demostrar la calidad del detector a un cliente. | Corpus ampliado a ≥ 200 samples categorizados por tipo (EMAIL, API_KEY, SSN, CREDIT_CARD, PERSON, IBAN, MEDICAL_RECORD). Pipeline en CI que corra recall_evaluator y falle si recall < umbral. Métricas publicadas en Prometheus con alerta. | 4 días | ⚠️ (30 samples, sin CI) | ❌ |

---

### Bloque C — Gobernanza enterprise

| ID | Tarea | Descripción | Criterio de aceptación | Esfuerzo | Desarrollado | Tests |
|---|---|---|---|---|---|---|
| **T5** | Sistema de waivers/excepciones | Hoy solo existe aprobar/rechazar un finding individual. No hay mecanismo para "permitir este tipo de hallazgo durante N días con aprobación del CISO". Sin esto, la plataforma es todo-o-nada, lo que genera fricción operacional inaceptable en enterprise. | Modelo `Waiver` en BD (finding_type, duration_days, ticket_id, approved_by, expires_at). `POST /v1/waivers`. OPA consulta waivers activos antes de escalar. Test: waiver activo evita escalado; waiver expirado no evita. | 4 días | ❌ | ❌ |
| **T7** | Particionado PostgreSQL | Las tablas `operations` y `findings` crecen indefinidamente. Para volumen enterprise (miles de scans/día) y cumplimiento de retención GDPR (borrado por período), el particionado es necesario. | Migración Alembic que añade particionado por `created_at` (RANGE MONTHLY) en `operations` y `findings`. Test de borrado por partición. | 1 día | ❌ | ❌ |

---

### Bloque D — Protocolo MCP enterprise

| ID | Tarea | Descripción | Criterio de aceptación | Esfuerzo | Desarrollado | Tests |
|---|---|---|---|---|---|---|
| **T8** | OAuth 2.1 + PKCE para MCP HTTP | El spec MCP exige OAuth 2.1 con PKCE cuando se usa transporte HTTP. Hoy el MCP Server usa `MCP_AUTH_TOKEN` estático. Eso es aceptable para demo interna pero no para un cliente enterprise que conecte su agente externo. | Keycloak configurado como Authorization Server con PKCE. `mcp/auth.py` valida `audience`, Resource Indicators, `client_id`. Token estático solo en modo `dev`. Test de flujo completo PKCE. | 5 días | ❌ | ❌ |
| **T9** | Consent management en MCP | El spec MCP dice: "el host debe controlar permisos y consentimiento; los servidores no deben ver más contexto del estrictamente necesario". Hoy el MCP Server acepta cualquier documento sin scope de consentimiento. | Claims de scope en token MCP: `scan:read`, `audit:read`, `review:write`. Validación por tool. Log de consentimiento en audit trail. Test: token sin `review:write` rechaza safecontext.approve. | 3 días | ❌ | ❌ |

---

### Bloque E — Mantenimiento técnico

| ID | Tarea | Descripción | Prioridad | Desarrollado |
|---|---|---|---|---|
| **T10a** | Python 3.13+ | Python 3.12 en security-fixes-only desde 2025. Migrar a 3.13 antes de F4 real. | Baja | ❌ |
| **T10b** | Next.js 15+ | Actualizar cuando haya smoke-test verde en staging. | Baja | ❌ |
| **T10c** | PostgreSQL 17+ | En el siguiente DR drill planificar upgrade. | Baja | ❌ |
| **T10d** | MinIO due diligence | Repositorio público archivado en abril 2026. ADR-011 abstrajo el storage correctamente. Evaluar AIStor o alternativa S3-compatible antes de primer cliente enterprise real. | Media | ❌ |

---

## 8. Deuda técnica documentada

| ID | Deuda | Impacto | Dónde está |
|---|---|---|---|
| **TECH-DEBT-001** | `actor_id` sentinel hardcodeado en `/v1/scan` y `/v1/review` | Audit trail no trazable por usuario real. Bloquea T2. | `apps/api/api/v1/scan.py:83`, `review.py:140` |
| **TECH-DEBT-002** | `MinIO` nombrado explícitamente en variables de entorno y comentarios | Cosmético — el código real usa `StoragePort` (ADR-011). Swap técnico es trivial. | `.env.example`, comentarios en workers |
| **TECH-DEBT-003** | Tokens MCP estáticos en modo dev y CI | Aceptable para desarrollo. Bloquea T8. | `apps/api/mcp/auth.py`, `.env.example` |
| **TECH-DEBT-004** | Corpus de evaluación con solo 30 samples | Insuficiente para demostrar recall a cliente enterprise. Bloquea T6. | `workers/tests/fixtures/corpus/corpus.json` |

---

## 9. ADR Index

| ADR | Decisión | Estado |
|---|---|---|
| ADR-001 | PostgreSQL como único sistema de registro | Cerrado |
| ADR-002 | Redis como broker efímero exclusivamente | Cerrado |
| ADR-003 | MCP Server implementado sobre FastAPI | Cerrado |
| ADR-004 | Agentes internos como única fuente de capacidad | Cerrado |
| ADR-005 | OPA/Rego para policy-as-code | Cerrado |
| ADR-006 | Docker Compose para desarrollo; K8s para Enterprise/HA | Cerrado |
| ADR-007 | Dramatiq sobre Redis como broker de workers | Cerrado |
| ADR-008 | MinIO con WORM + SSE para almacenamiento de artefactos | Cerrado |
| ADR-009 | OpenTelemetry + Prometheus para observabilidad | Cerrado |
| ADR-010 | Presidio + spaCy como detectores base, interfaz abstraída | Cerrado |
| ADR-011 | Port & Adapter pattern para Redis (BrokerPort, CachePort) y MinIO (StoragePort) | Cerrado |

---

## 10. Estado consolidado por dimensión

| Dimensión | Estado | Gap principal |
|---|---|---|
| Arquitectura | ✅ Completa | — |
| Backend API | ✅ Completa | T2: actor_id real |
| Workers / Agentes | ✅ Completa | T3: rescan, T4: capa determinística |
| Frontend UI | ✅ Completa | — |
| MCP Server | ⚠️ Funcional, no enterprise | T8: OAuth2.1/PKCE, T9: consent |
| Policy Engine | ✅ Completa | T5: waivers |
| Audit Trail | ⚠️ Funcional, trazabilidad parcial | T2: actor_id, T1: SARIF |
| Observabilidad | ✅ Completa | T6: corpus en CI |
| Supply Chain | ✅ Completa | — |
| DevSecOps / CI | ✅ Completa | — |
| Auth / Identidad | ✅ Completa | T8: PKCE MCP |
| Offline / Air-gapped | ✅ Completa | T10d: MinIO due diligence |
| Base de datos | ⚠️ Funcional | T7: particionado |
| Tests | ✅ 43 UI + API tests | T6: golden corpus en CI |

---

## 11. Resumen para nuevos agentes

**Madurez actual**: 3.5–4 / 5

**Lo que existe y funciona**: stack completo Docker Compose, FastAPI + Workers + PostgreSQL + Redis + MinIO + OPA + Keycloak + Vault + Harbor + Kubernetes + CI/CD + Frontend Next.js con OIDC.

**Lo que NO existe todavía** (tareas del replanteo):
- SARIF output (T1)
- actor_id real desde JWT (T2) — **tocar scan.py y review.py**
- Rescan post-sanitización (T3)
- Capa de reglas determinísticas pre-ML (T4)
- Sistema de waivers (T5)
- Golden corpus ≥ 200 samples en CI (T6)
- Particionado PostgreSQL (T7)
- OAuth 2.1 + PKCE en MCP (T8)
- Consent management MCP (T9)

**Antes de implementar cualquier cosa**: verifica que no esté ya implementado consultando los flags de esta tabla y leyendo el archivo correspondiente en el repo.

---

*Generado a partir de: DOC-0_UNIFIED.md · DOC-3_SPEC.md · deep-research-report.md · estado real del repositorio*
*Próxima actualización: al completar cualquier tarea T1–T10*
