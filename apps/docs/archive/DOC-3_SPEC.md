# DOC-3 · SafeContext — Spec Ejecutable
**Versión**: 0.2.0 · **Estado**: Activo · **Fecha**: 2026-05-17 · **Actualizado**: 2026-05-21
**Derivado de**: DOC-0 v0.2.0 + DOC-2 v0.1.1
**Audiencia**: Claude Code, Tech Lead, equipo de desarrollo
**Uso**: Este documento define los criterios de aceptación por fase. Para el estado actual de implementación (qué está hecho, qué está probado) ver `docs/ROADMAP.md`.

> **Estado general**: F1–F5 completadas ✅. Las tareas pendientes (T1–T10 del replanteo) están en `docs/ROADMAP.md §7`.

---

## Instrucción para el agente que lee este documento

Eres Claude Code. Este documento define el trabajo completo del proyecto SafeContext organizado por fases. Tu responsabilidad es:

1. Leer este documento completo antes de generar cualquier historia o tarea.
2. Respetar el orden de fases — F1 debe estar completa (todos los criterios en verde) antes de iniciar F2.
3. Para cada fase, generar historias de usuario y tareas técnicas con la granularidad suficiente para que un desarrollador pueda ejecutarlas sin ambigüedad.
4. Identificar dependencias entre tareas dentro de una fase y proponer paralelización cuando sea seguro.
5. Estimar el número mínimo de agentes especializados necesarios para ejecutar cada fase en paralelo.
6. Nunca asumir que un criterio de aceptación está cumplido si no hay evidencia verificable.

---

## F1 · Base segura ✅ COMPLETADA (4–6 semanas)

**Objetivo**: estructura técnica correcta, observabilidad básica, pipeline gate funcional. Sin esta fase, nada de lo que sigue tiene base sólida.

### Entregables y criterios de aceptación

#### E1.1 · Repositorio y estructura de proyecto

| Criterio | Pasa si |
|---|---|
| Repositorio inicializado con estructura de monorepo | `/apps/api`, `/apps/ui`, `/workers`, `/policies`, `/infra`, `/docs` existen |
| .gitignore excluye secretos y artefactos de build | Ningún secreto real en el repositorio inicial |
| Pre-commit hooks instalados | `detect-secrets`, `ruff`, `mypy`, `eslint` corren en cada commit |
| ADRs iniciales documentados | ADR-001 a ADR-010 en `/docs/adr/` con formato estándar |
| Glosario canónico disponible | `/docs/GLOSSARY.md` con todos los términos de DOC-0 §7 |

#### E1.2 · Modelo de dominio y esquema de base de datos

| Criterio | Pasa si |
|---|---|
| Schema PostgreSQL implementado | Tablas `operations`, `findings`, `redactions`, `artifacts`, `outbox` creadas con migraciones Alembic |
| RLS habilitado en todas las tablas | `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` verificable |
| pgAudit instalado y configurado | Logs de auditoría generados para operaciones de escritura |
| Índices en `trace_id`, `actor_id`, `operation_id` | EXPLAIN ANALYZE muestra uso de índices en queries típicas |

#### E1.3 · Backend API (FastAPI)

| Criterio | Pasa si |
|---|---|
| Endpoints de scan implementados | `POST /v1/scan` acepta documento y retorna findings con trace_id |
| Cada respuesta incluye trace_id | 100% de respuestas de operación incluyen `trace_id` en header y body |
| Cada operación registrada en PostgreSQL | Toda llamada a `/v1/scan` genera registro en `operations` antes de retornar |
| OpenAPI generada automáticamente | `/docs` accesible y completo sin configuración manual |
| Health check implementado | `GET /health` retorna status de dependencias (PG, Redis, MinIO) |
| Dockerfiles multi-stage para API | Imagen final < 200MB, sin herramientas de dev |

#### E1.4 · MCP Server (módulo FastAPI)

| Criterio | Pasa si |
|---|---|
| `safecontext.scan` implementado | Tool invocable desde cliente MCP con schema válido |
| `safecontext.sanitize` implementado | Tool retorna documento sanitizado + redaction_map |
| `safecontext.classify` implementado | Tool retorna nivel de sensibilidad por sección con justificación |
| Schema de tools en formato MCP estándar | Válido contra MCP spec actual |
| Autenticación básica en MCP Server | Requests sin token retornan 401 |
| Audit trail por actor_type 'mcp_agent' | Operaciones vía MCP registran `actor_type = 'mcp_agent'` en PostgreSQL |

#### E1.5 · Agentes internos (Workers Dramatiq)

| Criterio | Pasa si |
|---|---|
| Detector implementado con interfaz abstraída | `DetectorInterface` definida; Presidio/spaCy como implementación por defecto |
| Sanitizador implementado | Redacta spans detectados; escribe `redaction_type`, `policy_version` en PostgreSQL |
| Clasificador implementado | Asigna nivel de sensibilidad con justificación estructurada |
| Auditor implementado | Almacena artefactos en MinIO con WORM; registra digest en `artifacts` |
| Revisor implementado | Escala a estado `escalated` cuando `confidence < threshold` |
| Todos los workers son idempotentes | Re-procesar el mismo mensaje produce el mismo resultado sin duplicados |
| Outbox pattern implementado | PostgreSQL `outbox` es la fuente de encolar en Redis — Redis nunca es la fuente de verdad |
| DLQ configurada | Mensajes fallidos después de N reintentos van a Dead Letter Queue |

#### E1.6 · Policy Engine (OPA)

| Criterio | Pasa si |
|---|---|
| OPA desplegado como sidecar o servicio | API puede consultar OPA en cada operación |
| Política base implementada en Rego | Define umbrales de confianza, severidades y acciones por clase de dato |
| Tests de política implementados | `opa test` pasa con cobertura ≥ 80% de reglas |
| Política versionada con semver | `policy_version` en cada decisión corresponde a versión en repositorio |

#### E1.7 · Observabilidad

| Criterio | Pasa si |
|---|---|
| OTel SDK integrado en API y workers | Trazas distribuidas visibles en collector |
| trace_id propagado de API a workers | Un trace_id cubre el flujo completo API → worker → DB |
| Métricas Prometheus exportadas | API y workers exponen `/metrics` |
| Métrica de recall por clase de detector | `safecontext_detector_recall{class="EMAIL"}` visible en Prometheus |
| Dashboard Grafana básico | Latencia, throughput, errores y recall visibles |

#### E1.8 · Pipeline gate GitHub

| Criterio | Pasa si |
|---|---|
| GitHub Action implementada | Invoca `safecontext.scan` en push/PR |
| Pipeline retorna pass/block | Exit code 0 si limpio, 1 si hallazgos críticos |
| Reporte adjunto al PR | Hallazgos con explicación visibles como comment en el PR |
| Acción publicada en repositorio de acciones | Instalable con `uses: safecontext/action@v1` |

#### E1.9 · Infraestructura Docker Compose

| Criterio | Pasa si |
|---|---|
| `docker compose up` levanta el stack completo | API, UI, workers, PG, Redis, MinIO, OTel, Prometheus en < 3 min |
| Next.js custom cache handler configurado | Múltiples instancias de UI son consistentes |
| Reverse proxy nginx configurado | UI accesible en puerto 443 con TLS self-signed para desarrollo |
| Variables de entorno documentadas | `.env.example` completo, ningún secreto real |

### Contratos de interfaz que deben estar cerrados en F1

- `POST /v1/scan` — schema de request y response final (no se cambia en F2 sin versión)
- Tool schema MCP `safecontext.scan` — no se cambia en F2 sin versionado
- Schema de `operations`, `findings`, `redactions` — migraciones backward-compatible desde F2

### Métricas que deben estar instrumentadas en F1

- `safecontext_scan_duration_seconds` (histograma, p50/p95/p99)
- `safecontext_findings_total` (counter, por clase y severidad)
- `safecontext_detector_recall` (gauge, por clase)
- `safecontext_operations_total` (counter, por status)

### Gate de salida F1 → F2 ✅ VERIFICADO

**Todos** los siguientes deben ser verdaderos:
- [x] 100% de operaciones de scan generan `trace_id` + `artifact_digest` + `policy_version`
- [x] Redis no almacena ningún estado que no pueda perderse sin impacto
- [x] `docker compose up` produce despliegue completo y reproducible
- [x] GitHub Action funcional en repositorio de prueba
- [x] OPA con tests pasando
- [x] Recall ≥ 0.90 en corpus de prueba etiquetado (clases EMAIL, API_KEY, PII_NAME)

---

## F2 · Producto endurecido ✅ COMPLETADA (6–8 semanas)

**Objetivo**: operación repetible, backup/restore probado, auditoría detallada, cache distribuido, jobs resilientes.

### Entregables y criterios de aceptación

#### E2.1 · Auditoría y compliance

| Criterio | Pasa si |
|---|---|
| pgAudit con configuración completa | Todas las escrituras en tablas críticas auditadas |
| Exportación de audit trail por trace_id | `GET /v1/audit/{trace_id}` retorna evidencia completa en JSON firmado |
| Retención configurable por clase de dato | Política de retención activa y verificable |

#### E2.2 · Almacenamiento de artefactos (MinIO)

| Criterio | Pasa si |
|---|---|
| WORM / object locking habilitado | Artefactos de evidencia no pueden ser modificados o eliminados |
| SSE configurado | Todos los objetos almacenados con cifrado del lado servidor |
| Retención por bucket configurada | Objetos eliminados automáticamente según política |
| Versioning habilitado | Cada nueva versión de artefacto genera nuevo objeto; el anterior se conserva |

#### E2.3 · Resiliencia de workers

| Criterio | Pasa si |
|---|---|
| Retries con backoff exponencial configurados | Worker reintenta N veces con backoff antes de DLQ |
| DLQ monitoreada con alerta | Alerta Prometheus cuando DLQ > 0 durante > 5 min |
| Hot-reload de políticas OPA | Cambio de política no requiere reinicio de workers |
| Graceful shutdown en workers | Worker completa tarea en curso antes de apagarse |

#### E2.4 · Backup y disaster recovery

| Criterio | Pasa si |
|---|---|
| Backup de PostgreSQL automatizado | Backup diario con WAL archiving |
| Restore probado exitosamente | Restore completo en entorno de prueba < 1 hora |
| Backup de MinIO automatizado | Política de replicación o snapshot configurada |
| Runbook de DR documentado | Pasos verificables, sin ambigüedad |

#### E2.5 · Cache distribuido Next.js

| Criterio | Pasa si |
|---|---|
| Custom cache handler implementado | Apunta a Redis, no a disco local |
| Test de consistencia multiinstancia | Dos instancias de UI retornan el mismo contenido ante el mismo request |

#### E2.6 · Revisión humana (UI)

| Criterio | Pasa si |
|---|---|
| UI muestra hallazgos escalados con explicación completa | rule_id, detector, confianza, span afectado visible |
| Revisor puede aprobar/rechazar con justificación | Aprobación registrada en `redactions.approved_by` |
| Flujo bloqueado hasta aprobación para hallazgos escalados | Estado `escalated` no avanza sin acción humana |

#### E2.7 · Tools MCP adicionales

| Criterio | Pasa si |
|---|---|
| `safecontext.audit` implementado | Retorna evidencia completa de operación dado trace_id |
| `safecontext.policy.get` implementado | Retorna política activa versionada |

### Gate de salida F2 → F3 ✅ VERIFICADO

**Todos** los siguientes deben ser verdaderos:
- [x] Restore de PostgreSQL probado y exitoso en entorno aislado
- [x] pgAudit generando logs de escritura en todas las tablas críticas
- [x] Cache multiinstancia de Next.js consistente en test
- [x] WORM + SSE activos en MinIO
- [x] Jobs idempotentes verificados con test de re-entrega
- [x] Recall ≥ 0.95 en corpus etiquetado (clases críticas)

---

## F3 · Supply chain y gobierno ✅ COMPLETADA (4–6 semanas)

**Objetivo**: cadena de suministro verificable, 0 secretos estáticos, deploy gate activo.

### Entregables y criterios de aceptación

#### E3.1 · OIDC y secretos

| Criterio | Pasa si |
|---|---|
| GitHub Actions usa OIDC | Sin secrets estáticos en repositorio ni en configuración de Actions |
| 0 secretos de larga vida en CI/CD | Auditoría de secretos pasa sin hallazgos |
| Comunicación interna API ↔ workers autenticada | mTLS o token interno de corta vida |

#### E3.2 · SBOM y firma

| Criterio | Pasa si |
|---|---|
| SBOM generado en cada build | Archivo SBOM adjunto a cada imagen |
| Imágenes firmadas con Cosign | `cosign verify` pasa para toda imagen en registry |
| Provenance SLSA generado | Attestation verificable para cada build |
| Deploy bloqueado si firma falla | Pipeline con deployment protection rule activa |

#### E3.3 · Deploy gate con aprobación humana

| Criterio | Pasa si |
|---|---|
| Deployment protection rules activas en GitHub | Deploy a producción requiere aprobador designado |
| Excepciones a políticas requieren aprobación registrada | Toda excepción tiene trace_id, aprobador y justificación |
| Escaneo de vulnerabilidades en pipeline | Trivy corre en cada build; hallazgos críticos bloquean deploy |

#### E3.4 · Manifiestos Kubernetes generados

| Criterio | Pasa si |
|---|---|
| Compose Bridge genera manifiestos K8s | `docker compose convert` produce manifiestos válidos |
| NetworkPolicy deny-all por defecto | Validación de NetworkPolicy en CI |
| HPA configurado para API y workers | Escalado automático basado en métricas de cola |

### Gate de salida F3 → F4 ✅ VERIFICADO

**Todos** los siguientes deben ser verdaderos:
- [x] 100% de imágenes firmadas con SBOM adjunto
- [x] 0 secretos estáticos en CI/CD
- [x] Deploy bloqueado si política o firma falla
- [x] Excepciones auditadas con aprobador registrado

---

## F4 · Enterprise operativo ✅ COMPLETADA (6–8 semanas)

**Objetivo**: SSO/MFA, segregación de funciones, SLOs con error budget, DR verificado, runbooks operativos.

### Entregables y criterios de aceptación

#### E4.1 · Identidad y acceso

| Criterio | Pasa si |
|---|---|
| SSO/MFA habilitado para UI | Acceso sin MFA rechazado |
| Roles implementados | Viewer, Reviewer, PolicyEditor, Admin con permisos distintos y verificados |
| Segregación de funciones auditada | Un usuario no puede aprobar su propia excepción |
| Rate limiting por client_id en MCP Server | Requests por encima del límite retornan 429 |

#### E4.2 · KMS y gestión de claves

| Criterio | Pasa si |
|---|---|
| KMS integrado para claves MinIO | Rotación de claves sin downtime |
| Rotación de claves documentada y probada | Runbook ejecutado exitosamente |

#### E4.3 · SLOs y error budget

| Criterio | Pasa si |
|---|---|
| SLOs definidos y medidos | Disponibilidad 99.9%, latencia p95 < 5s documentados y monitorizados |
| Error budget dashboard | Consumo de error budget visible en Grafana |
| Alertas de SLO configuradas | Alerta cuando error budget < 50% del período |

#### E4.4 · DR verificado

| Criterio | Pasa si |
|---|---|
| RTO < 15 min verificado en drill | Drill ejecutado, RTO documentado |
| RPO < 5 min verificado | WAL archiving con intervalo < 5 min verificado |
| DR drill trimestral programado | Calendario en runbook operativo |

#### E4.5 · Versionado de tools MCP

| Criterio | Pasa si |
|---|---|
| Tools MCP versionados | Clientes pueden fijar `tool_version` en request |
| Backward compatibility mantenida por 2 versiones | Test de compatibilidad con cliente en versión N-1 |

#### E4.6 · `safecontext.approve` implementado

| Criterio | Pasa si |
|---|---|
| Tool MCP de aprobación implementado | Agentes con permisos delegados pueden aprobar hallazgos |
| Aprobación registrada con identidad del agente | `approved_by_agent_id` en `redactions` |

### Gate de salida F4 → F5 ✅ VERIFICADO

**Todos** los siguientes deben ser verdaderos:
- [x] SSO/MFA habilitado y verificado
- [x] RTO < 15 min en DR drill
- [x] SLOs medidos con error budget activo
- [x] Revisión humana obligatoria para hallazgos críticos funcionando
- [x] Evidencia exportable para auditoría probada

---

## F5 · Desconectado regulado ✅ COMPLETADA (6–10 semanas)

**Objetivo**: instalación, operación, actualización y rollback completos sin internet.

### Entregables y criterios de aceptación

#### E5.1 · Registry privado

| Criterio | Pasa si |
|---|---|
| Harbor (o equivalente) desplegado localmente | Todas las imágenes disponibles sin acceso a internet |
| Firma verificable desde registry privado | `cosign verify` pasa contra registry local |

#### E5.2 · CI/CD self-hosted

| Criterio | Pasa si |
|---|---|
| Runners GitHub/GitLab self-hosted configurados | Pipeline completo ejecuta sin acceso a internet |
| OIDC funcional en entorno aislado | Autenticación de pipeline sin dependencia externa |

#### E5.3 · Modelos NLP/ML offline

| Criterio | Pasa si |
|---|---|
| Modelos Presidio/spaCy/Transformers empaquetados | Descarga desde registry local, no desde internet |
| Actualización de modelos documentada | Proceso de bundle y distribución sin internet |

#### E5.4 · Bundle de actualización y rollback

| Criterio | Pasa si |
|---|---|
| Proceso de bundle documentado | Script genera bundle autónomo con todas las dependencias |
| Actualización probada sin internet | Upgrade de versión N a N+1 sin acceso externo |
| Rollback probado sin internet | Rollback a versión N exitoso sin acceso externo |

#### E5.5 · DR drill air-gapped

| Criterio | Pasa si |
|---|---|
| DR drill completo en entorno sin internet | Restore completo, RTO verificado, sin conexión externa |

### Gate de salida F5 ✅ VERIFICADO (certificación Enterprise air-gapped)

**Todos** los siguientes deben ser verdaderos:
- [x] Instalación completa sin internet documentada y probada
- [x] Actualización y rollback offline probados
- [x] DR drill exitoso en entorno air-gapped
- [x] Recall ≥ 0.98 en clases críticas con modelos offline

---

## Tool definitions MCP (schema formal)

```json
{
  "tools": [
    {
      "name": "safecontext.scan",
      "version": "1.0.0",
      "description": "Scan a document for PII, secrets, and sensitive data. Returns findings with full explanation.",
      "input_schema": {
        "type": "object",
        "required": ["document", "policy_name"],
        "properties": {
          "document": {
            "type": "string",
            "description": "Document content to scan (text or base64 for binary)"
          },
          "document_encoding": {
            "type": "string",
            "enum": ["text", "base64"],
            "default": "text"
          },
          "policy_name": {
            "type": "string",
            "description": "Name of the OPA policy to apply"
          },
          "policy_version": {
            "type": "string",
            "description": "Specific policy version (semver). Defaults to latest."
          }
        }
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "trace_id": { "type": "string", "format": "uuid" },
          "artifact_digest": { "type": "string", "description": "SHA-256 of input document" },
          "policy_version": { "type": "string" },
          "findings": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": { "type": "string", "format": "uuid" },
                "detector": { "type": "string" },
                "rule_id": { "type": "string" },
                "span_start": { "type": "integer" },
                "span_end": { "type": "integer" },
                "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
                "severity": { "type": "string", "enum": ["low", "medium", "high", "critical"] },
                "explanation": { "type": "object" }
              }
            }
          },
          "requires_human_review": { "type": "boolean" }
        }
      }
    },
    {
      "name": "safecontext.sanitize",
      "version": "1.0.0",
      "description": "Sanitize a document based on scan findings. Returns sanitized document and redaction map.",
      "input_schema": {
        "type": "object",
        "required": ["trace_id", "redaction_type"],
        "properties": {
          "trace_id": { "type": "string", "format": "uuid" },
          "redaction_type": { "type": "string", "enum": ["mask", "remove", "replace"] },
          "replacement_token": {
            "type": "string",
            "description": "Token to use for replacement (only when redaction_type=replace)"
          }
        }
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "trace_id": { "type": "string", "format": "uuid" },
          "sanitized_document": { "type": "string" },
          "sanitized_artifact_digest": { "type": "string" },
          "redaction_map": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "finding_id": { "type": "string", "format": "uuid" },
                "span_start": { "type": "integer" },
                "span_end": { "type": "integer" },
                "redaction_type": { "type": "string" },
                "policy_version": { "type": "string" }
              }
            }
          }
        }
      }
    },
    {
      "name": "safecontext.classify",
      "version": "1.0.0",
      "description": "Classify document sensitivity level by section.",
      "input_schema": {
        "type": "object",
        "required": ["document"],
        "properties": {
          "document": { "type": "string" }
        }
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "trace_id": { "type": "string", "format": "uuid" },
          "overall_level": { "type": "string", "enum": ["public", "internal", "confidential", "restricted"] },
          "sections": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "section_id": { "type": "integer" },
                "level": { "type": "string" },
                "justification": { "type": "string" }
              }
            }
          }
        }
      }
    },
    {
      "name": "safecontext.audit",
      "version": "1.0.0",
      "description": "Retrieve complete audit evidence for an operation by trace_id.",
      "input_schema": {
        "type": "object",
        "required": ["trace_id"],
        "properties": {
          "trace_id": { "type": "string", "format": "uuid" }
        }
      }
    },
    {
      "name": "safecontext.policy.get",
      "version": "1.0.0",
      "description": "Get active policy definition by name and optional version.",
      "input_schema": {
        "type": "object",
        "required": ["policy_name"],
        "properties": {
          "policy_name": { "type": "string" },
          "policy_version": { "type": "string" }
        }
      }
    }
  ]
}
```

---

## Checklist enterprise por dimensión

| Dimensión | F1 | F2 | F3 | F4 | F5 |
|---|---|---|---|---|---|
| Arquitectura | Separación API/workers/DB definida | Outbox pattern activo | Manifiestos K8s generados | HPA + PodDisruptionBudget | N/A |
| Seguridad | TLS, RLS, auth básica | pgAudit, SSE MinIO | OIDC, SBOM, firma, Trivy | SSO/MFA, KMS, roles | Offline auth |
| Observabilidad | OTel + Prometheus básico | Recall metrics, alertas DLQ | SLO dashboard | Error budget activo | Offline telemetry |
| Compliance | trace_id + artifact_digest | pgAudit + exportación | SLSA provenance | Segregación funciones | Audit offline |
| DevSecOps | Pre-commit, Dockerfiles | Tests de política OPA | SBOM + Cosign + deploy gate | Versionado tools MCP | CI self-hosted |
| Resiliencia | Health checks | Backup/restore probado | DR preparado | DR drill ≤ 15 min | DR air-gapped |
| IA/ML | Detector con interfaz abstraída | Recall ≥ 0.95 + alertas | — | — | Recall ≥ 0.98 offline |
| Supply chain | Trivy en build | — | SBOM + firma + SLSA | — | Registry privado |

---

*Derivado de DOC-0 v0.2.0 + DOC-2 v0.1.1*
*Los criterios de aceptación siguen siendo válidos como referencia.*
*Para estado de implementación y tareas pendientes ver `docs/ROADMAP.md`*
