# DOC-0 · SafeContext — Documento Unificado
**Versión**: 0.1.0 · **Estado**: Draft · **Fecha**: 2026-05-17
**Autoridad**: Este documento es la fuente de verdad. PRD, SAD y Spec Ejecutable son derivados.
Ante contradicción entre documentos derivados y este, este prevalece.

---

## 1. Visión y propósito

SafeContext es una plataforma Enterprise-grade de sanitización, clasificación y gobierno de documentos y datos sensibles, diseñada para ser consumida tanto por humanos como por agentes de inteligencia artificial.

**Propósito central**: garantizar que ningún documento sensible llegue a un modelo de IA, pipeline de CI/CD o sistema externo sin haber pasado por un proceso verificable, auditable y explicable de detección, sanitización y aprobación.

**Diferencial competitivo**:
- SafeContext no es un escáner de secretos. Es un sistema de gobierno de contexto para entornos donde la IA consume documentos.
- Expone sus capacidades como **MCP Server**, lo que permite que cualquier agente LLM compatible (Claude, Codex, GitHub Copilot, etc.) consuma SafeContext como herramienta nativa, sin lock-in de interfaz.
- Opera con agentes internos especializados que corren localmente, garantizando compatibilidad con entornos air-gapped y despliegues regulados.
- Toda decisión es explicable, auditable e inmutable.

---

## 2. Problema que resuelve

| Problema | Consecuencia sin SafeContext |
|---|---|
| Documentos con PII, secretos o datos confidenciales ingresan a modelos de IA | Fuga de datos no detectable, violación de GDPR/HIPAA |
| Los pipelines de CI/CD no verifican qué contexto envían a herramientas de IA | Exposición de credenciales, configuraciones internas, datos de clientes |
| Las decisiones de sanitización son opacas (modelo decide, nadie sabe por qué) | No auditables, no defendibles ante compliance |
| Los agentes LLM no tienen forma estándar de verificar la seguridad del contexto que consumen | El agente opera sobre datos no validados |
| Las soluciones existentes requieren enviar datos a SaaS externos para procesarlos | Incompatible con entornos regulados y air-gapped |

---

## 3. Usuarios y audiencias

### 3.1 Usuarios humanos

| Perfil | Interacción principal | Necesidad crítica |
|---|---|---|
| **Desarrollador** | UI web, pipeline gate | Saber qué fue detectado y por qué antes de que su código llegue a producción |
| **Arquitecto / Tech Lead** | Revisión de políticas, excepciones | Control sobre reglas de sanitización y umbrales de confianza |
| **Compliance / Seguridad** | Audit trail, exportación de evidencia | Evidencia inmutable de cada decisión para auditorías |
| **Operador** | Monitoreo, runbooks, DR | Observabilidad y recuperación ante fallas |

### 3.2 Consumidores agente (no humanos)

| Agente | Modo de integración | Caso de uso típico |
|---|---|---|
| **Claude (Anthropic)** | MCP Server | Verificar contexto antes de procesar documentos |
| **GitHub Copilot / Codex** | MCP Server | Gate de sanitización antes de generar código sobre datos sensibles |
| **GitHub Actions** | MCP Server / REST API | Pipeline gate: bloquear merge si el contexto no está sanitizado |
| **GitLab CI / Azure DevOps** | MCP Server / REST API | Mismo patrón que GitHub Actions |
| **Agente custom del cliente** | MCP Server | Cualquier agente LLM del cliente que implemente el protocolo MCP |

### 3.3 Agentes internos de SafeContext

Los agentes internos son la **unidad de capacidad** del producto. No son integraciones externas. Son componentes propios, especializados, que corren localmente.

| Agente interno | Responsabilidad | Autonomía |
|---|---|---|
| **Detector** | Identificar PII, secretos, datos sensibles en documentos | Alta — opera sin intervención humana en casos claros |
| **Sanitizador** | Redactar, enmascarar o eliminar contenido detectado | Alta — ejecuta según política versionada |
| **Clasificador** | Asignar nivel de sensibilidad al documento y sus secciones | Alta |
| **Auditor** | Registrar cada decisión con trace_id, policy_version, artifact_digest, actor | Total — nunca omite registro |
| **Revisor** | Escalar a revisión humana cuando confianza < umbral o impacto > threshold | Opera como gate — bloquea hasta aprobación |

**Principio invariante**: ninguna lógica de negocio vive en la capa UI ni en el MCP Server. UI y MCP son exclusivamente capas de entrega. Los agentes internos son la única fuente de capacidad.

---

## 4. Modelo funcional consolidado

### 4.1 Capacidades core

| Capacidad | Descripción | Requisito enterprise asociado |
|---|---|---|
| **Detección** | Identificación de PII, secretos, datos regulados usando reglas + NLP/ML | Recall ≥ 0.98 en clases críticas (Enterprise-grade) |
| **Sanitización** | Redacción, enmascaramiento o eliminación con justificación explícita | Cada redacción lleva rule_id, detector, confianza, versión de política |
| **Clasificación** | Nivel de sensibilidad por documento y sección | Explicable, versionado, auditable |
| **Gobierno de políticas** | Reglas versionadas, testeadas, desplegadas por pipeline | Policy-as-code con OPA/Rego |
| **Revisión humana** | Gate obligatorio para hallazgos de alta criticidad o baja confianza | Aprobación registrada con actor, timestamp, trace_id |
| **Auditoría inmutable** | Registro de toda operación crítica | trace_id + artifact_digest + policy_version + actor + timestamp |
| **Operación offline** | Todas las capacidades funcionan sin dependencias externas | Air-gapped completo |

### 4.2 Superficies de consumo

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

**La UI no es una superficie separada en términos de capacidad.** Es un cliente privilegiado que consume los mismos agentes internos que el MCP Server expone. Esto garantiza paridad funcional entre interfaces.

### 4.3 MCP Server — herramientas expuestas

| Tool MCP | Input | Output | Garantías |
|---|---|---|---|
| `safecontext.scan` | documento (texto/binario), política | hallazgos con explicación, nivel de confianza | Audit trail automático |
| `safecontext.sanitize` | documento + hallazgos + política | documento sanitizado + redaction_map | Inmutable, versionado |
| `safecontext.classify` | documento | nivel de sensibilidad + justificación | Explicable por sección |
| `safecontext.approve` | hallazgo_id + decisión humana | aprobación registrada | Requiere identidad verificada |
| `safecontext.audit` | trace_id | evidencia completa de la operación | Solo lectura, inmutable |
| `safecontext.policy.get` | nombre de política | política activa versionada | Versionado semántico |

### 4.4 Flujos principales

**Flujo humano (UI)**:
```
Usuario sube documento → Detector analiza → Clasificador asigna nivel →
Si confianza < umbral → Revisor escala a humano → Aprobación registrada →
Sanitizador redacta → Auditor registra → Documento sanitizado disponible
```

**Flujo agente externo (MCP)**:
```
Agente invoca safecontext.scan → Detector analiza → Respuesta con hallazgos →
Agente invoca safecontext.sanitize → Documento sanitizado + redaction_map →
Agente usa documento sanitizado con garantía de trazabilidad
```

**Flujo pipeline CI/CD**:
```
Commit/PR trigger → GitHub Action invoca safecontext.scan →
Si hallazgos críticos → Pipeline bloqueado, reporte generado →
Si aprobación requerida → Gate humano en pipeline →
Si limpio → Pipeline continúa con evidencia de escaneo adjunta
```

---

## 5. Modelo técnico consolidado

### 5.1 Stack y decisiones irrevocables

| Componente | Tecnología | Versión mínima | Justificación | Lock-in |
|---|---|---|---|---|
| Backend | FastAPI + asyncio | Python 3.12 | High performance, OpenAPI implícita, ecosistema ML | Bajo — interfaz REST estándar |
| Frontend | Next.js + TypeScript | Next.js 14+ | SSR, streaming, self-hosting, Tailwind/shadcn | Medio — sustituible por cualquier cliente MCP |
| Base de datos | PostgreSQL | 15+ | JSONB, RLS, pgAudit, HA, TLS | Bajo — SQL estándar |
| Cola/Workers | Redis (broker) + Dramatiq | Redis 7+ | Broker efímero, no fuente de verdad | Bajo — Dramatiq soporta RabbitMQ |
| Almacenamiento de artefactos | MinIO | AGPL o comercial | S3-compatible, WORM, erasure coding, SSE | Bajo — S3-compatible |
| Motor de políticas | OPA / Rego | OPA 0.60+ | Policy-as-code, versionado, testeable | Medio — Rego es DSL propio |
| Observabilidad | OpenTelemetry + Prometheus | — | Estándar de industria, vendor-neutral | Ninguno |
| Orquestación | Docker Compose → Kubernetes | — | Compose para desarrollo/single-node; K8s para HA/multi-tenant | Bajo |
| MCP Server | Implementación propia sobre FastAPI | MCP spec actual | Exposición de agentes internos como tools | Ninguno — protocolo abierto |
| NLP/ML detección | Presidio + spaCy + Transformers | — | Modular, reemplazable por detector custom | Bajo — interfaz de detector abstraída |

### 5.2 Principios arquitecturales no negociables

1. **PostgreSQL es el único sistema de registro**. Redis es efímero — nunca fuente de verdad para decisiones, auditoría o jobs.
2. **Los agentes internos son la única fuente de capacidad**. UI y MCP son capas de entrega sin lógica de negocio.
3. **Toda decisión es explicable**. Ningún resultado sale sin rule_id, detector, confianza, policy_version.
4. **Toda operación crítica genera audit trail**. trace_id + artifact_digest + actor + timestamp — sin excepciones.
5. **El producto opera sin internet**. Ningún flujo crítico depende de SaaS externo.
6. **Las políticas son código**. Versionadas, testeadas, desplegadas por pipeline, evaluadas por OPA.
7. **La revisión humana es un gate, no una opción**. Para hallazgos de alta criticidad o baja confianza, el flujo se bloquea hasta aprobación.

### 5.3 Controles enterprise no negociables

| Control | Implementación | Evidencia exigible |
|---|---|---|
| Zero Trust | Autenticación explícita en cada operación, incluso entre componentes internos | Logs de authz por operación |
| SSO/MFA | OIDC + MFA obligatorio para acceso humano | Configuración auditada |
| Secretos centralizados | Sin secretos de larga vida en CI/CD; OIDC para pipelines | 0 secretos estáticos en repositorio |
| SBOM | Generado en cada build | Archivo SBOM por imagen |
| Firma de artefactos | Cosign en toda imagen y artefacto | Verificación en deploy gate |
| Supply chain / SLSA | Provenance en cada build | Attestation verificable |
| Auditoría detallada | pgAudit en PostgreSQL | Logs exportables e inmutables |
| Cifrado en reposo | SSE en MinIO, cifrado en PostgreSQL | Configuración auditada |
| Retención de datos | Por clase de dato, configurable, aplicada automáticamente | Política documentada y activa |
| Operación air-gapped | Registry privado, runners self-hosted, bundles offline | DR drill exitoso sin internet |

---

## 6. Fases de madurez

| Fase | Duración | Estado de SafeContext | Criterio de graduación |
|---|---|---|---|
| **F1 · Base segura** | 4–6 sem | MVP estructurado | Toda operación genera trace_id + artifact_digest; Redis deja de ser fuente de verdad; despliegue reproducible |
| **F2 · Producto endurecido** | 6–8 sem | Producto | Restore probado; auditoría detallada; caché multiinstancia; artefactos cifrados; jobs idempotentes |
| **F3 · Supply chain y gobierno** | 4–6 sem | Producto seguro | 100% imágenes firmadas + SBOM; 0 secretos estáticos; deploy gate activo; excepciones auditadas |
| **F4 · Enterprise operativo** | 6–8 sem | Enterprise | RTO/RPO verificados; revisión humana activa; SSO/MFA; evidencia exportable; runbooks operativos |
| **F5 · Desconectado regulado** | 6–10 sem | Enterprise air-gapped | Instalación completa sin internet; actualización y rollback offline probados |

**Duración total estimada**: 26–38 semanas desde F1 hasta Enterprise air-gapped completo.

---

## 7. Glosario canónico

| Término | Definición en SafeContext |
|---|---|
| **artifact_digest** | Hash SHA-256 del artefacto procesado. Inmutable. Parte de todo audit trail. |
| **trace_id** | Identificador de correlación que une todas las operaciones de un flujo completo. |
| **policy_version** | Versión semántica de la política OPA/Rego activa en el momento de la decisión. |
| **hallazgo** | Resultado de detección: span afectado, detector, rule_id, confianza, política aplicada. |
| **redaction_map** | Mapa de todas las redacciones aplicadas: posición, tipo, justificación, versión de política. |
| **gate** | Punto de control que bloquea el flujo hasta que se cumple una condición verificable. |
| **agente interno** | Componente propio de SafeContext que ejecuta una capacidad especializada localmente. |
| **MCP Server** | Superficie de integración que expone los agentes internos como tools consumibles por agentes LLM. |
| **sistema de registro** | PostgreSQL — única fuente de verdad para decisiones, auditoría y estado durable. |
| **sistema efímero** | Redis — broker y cache transitorio. Nunca fuente de verdad. |

---

## 8. ADR Index

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

---

*Documento generado a partir de: Madurez técnica de SafeContext (deep-research-report.md)*
*Próxima revisión requerida: antes de iniciar F2*
