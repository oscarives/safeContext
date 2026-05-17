# DOC-1 · SafeContext — Product Requirements Document (Enterprise)
**Versión**: 0.1.0 · **Estado**: Draft · **Fecha**: 2026-05-17
**Derivado de**: DOC-0 v0.1.0
**Audiencia**: Stakeholders, Product Owner, Tech Lead, Compliance

---

## 1. Contexto de negocio

### 1.1 Problema central

Las organizaciones que adoptan IA generativa para procesar documentos internos enfrentan un problema estructural: no existe un mecanismo estandarizado, auditable y enterprise-grade para garantizar que el contexto que llega a un modelo de IA no contiene datos sensibles, PII, secretos o información regulada.

Las soluciones actuales son:
- **Escáneres de secretos** (detect-secrets, truffleHog): detectan credenciales en código, no documentos de negocio ni contextos de IA.
- **DLP corporativos** (Symantec, Forcepoint): no tienen integración nativa con pipelines de IA ni con protocolos de agentes (MCP).
- **Sanitización manual**: no escalable, no auditable, dependiente de criterio humano.

### 1.2 Oportunidad

SafeContext ocupa un espacio no cubierto: **gobierno de contexto para pipelines de IA**. El diferencial es:
1. Expone capacidades como **MCP Server** — compatible con cualquier agente LLM sin lock-in.
2. Opera **localmente** — viable en entornos air-gapped y regulados.
3. Toda decisión es **explicable y auditable** — defendible ante compliance.
4. Integra con **pipelines CI/CD** como gate de seguridad pre-merge.

---

## 2. Usuarios objetivo

### 2.1 Perfiles humanos

**P1 · Desarrollador**
- Contexto: trabaja con repositorios que contienen documentación, configuración y datos que luego son consumidos por herramientas de IA (Copilot, Claude, Codex).
- Necesidad: saber antes del merge si su contexto es seguro para ser procesado por IA.
- Punto de dolor: actualmente no tiene visibilidad de qué datos sensibles pueden estar en el contexto que envía a una herramienta de IA.
- Interacción con SafeContext: pipeline gate en PR, UI para revisión de hallazgos, MCP tool en su entorno de desarrollo.

**P2 · Arquitecto / Tech Lead**
- Contexto: define políticas de seguridad, umbrales de confianza y reglas de sanitización para el equipo.
- Necesidad: control sobre las reglas que gobiernan qué se detecta, cómo se sanitiza y cuándo se requiere revisión humana.
- Punto de dolor: las políticas actuales son informales, no versionadas y no auditables.
- Interacción: UI de gestión de políticas, pipeline de deployment de reglas OPA/Rego.

**P3 · Compliance / Seguridad**
- Contexto: responsable de garantizar cumplimiento GDPR, HIPAA, SOC2 u otros marcos.
- Necesidad: evidencia exportable, inmutable y verificable de cada decisión de sanitización.
- Punto de dolor: no puede demostrar ante una auditoría que los datos sensibles fueron tratados correctamente antes de llegar a un modelo de IA.
- Interacción: UI de audit trail, exportación de evidencia, reportes de cobertura.

**P4 · Operador**
- Contexto: responsable de disponibilidad, monitoreo y recuperación del sistema.
- Necesidad: observabilidad completa, runbooks claros y capacidad de DR probada.
- Punto de dolor: sistemas de IA sin SLOs definidos ni métricas de calidad del procesamiento.
- Interacción: dashboards Prometheus, alertas, runbooks operativos.

### 2.2 Consumidores agente

**A1 · Agente LLM externo (Claude, Codex, Copilot, custom)**
- Interacción: invoca tools del MCP Server antes de procesar documentos.
- Necesidad: certeza de que el documento que va a procesar ya fue sanitizado y tiene trazabilidad.

**A2 · GitHub Actions / GitLab CI / Azure DevOps**
- Interacción: invoca safecontext.scan como gate en pipeline.
- Necesidad: respuesta binaria (pass/block) con evidencia adjunta.

**A3 · Agente custom del cliente enterprise**
- Interacción: consume MCP Server con autenticación OIDC.
- Necesidad: integración sin fricción, rate limiting predecible, audit trail propio.

---

## 3. Requisitos funcionales

### 3.1 Superficie UI Web

| ID | Requisito | Prioridad | Fase |
|---|---|---|---|
| RF-UI-01 | El usuario puede subir un documento y ver hallazgos con explicación completa (detector, rule_id, confianza, política) | Must | F1 |
| RF-UI-02 | El usuario puede ver el documento sanitizado con redaction_map visual | Must | F1 |
| RF-UI-03 | El revisor puede aprobar o rechazar hallazgos de baja confianza con justificación registrada | Must | F1 |
| RF-UI-04 | El Tech Lead puede crear, editar y versionar políticas OPA/Rego desde la UI | Should | F2 |
| RF-UI-05 | Compliance puede exportar el audit trail completo de una operación dado un trace_id | Must | F2 |
| RF-UI-06 | El operador tiene dashboard con métricas de calidad del sanitizado, latencia y errores | Should | F2 |
| RF-UI-07 | SSO/MFA obligatorio para acceso a la UI | Must | F4 |
| RF-UI-08 | Segregación de funciones: roles Viewer, Reviewer, PolicyEditor, Admin | Must | F4 |

### 3.2 Superficie MCP Server

| ID | Requisito | Prioridad | Fase |
|---|---|---|---|
| RF-MCP-01 | Exponer `safecontext.scan` con input documento y output hallazgos explicados | Must | F1 |
| RF-MCP-02 | Exponer `safecontext.sanitize` con output documento sanitizado + redaction_map | Must | F1 |
| RF-MCP-03 | Exponer `safecontext.classify` con output nivel de sensibilidad por sección | Must | F1 |
| RF-MCP-04 | Exponer `safecontext.audit` para recuperar evidencia de operación por trace_id | Must | F2 |
| RF-MCP-05 | Exponer `safecontext.policy.get` para obtener política activa versionada | Should | F2 |
| RF-MCP-06 | Autenticación OAuth2/OIDC obligatoria para todo cliente MCP | Must | F3 |
| RF-MCP-07 | Rate limiting configurable por cliente/agente | Must | F3 |
| RF-MCP-08 | Audit trail por identidad de agente (no solo por usuario humano) | Must | F3 |
| RF-MCP-09 | Versionado semántico de tools — los clientes pueden fijar versión de tool | Should | F4 |
| RF-MCP-10 | `safecontext.approve` para que agentes con permisos delegados registren aprobaciones | Should | F4 |

### 3.3 Superficie Pipeline CI/CD

| ID | Requisito | Prioridad | Fase |
|---|---|---|---|
| RF-CI-01 | GitHub Action oficial que invoca safecontext.scan en PR/push | Must | F1 |
| RF-CI-02 | Pipeline retorna pass/block con reporte de hallazgos adjunto al PR | Must | F1 |
| RF-CI-03 | Gate de aprobación humana en pipeline para hallazgos críticos | Must | F2 |
| RF-CI-04 | Autenticación OIDC — sin secretos estáticos en CI | Must | F3 |
| RF-CI-05 | SBOM y firma de artefactos como parte del pipeline de SafeContext mismo | Must | F3 |
| RF-CI-06 | Soporte para GitLab CI y Azure DevOps | Should | F4 |

### 3.4 Agentes internos

| ID | Requisito | Prioridad | Fase |
|---|---|---|---|
| RF-AG-01 | Detector identifica PII, secretos, datos regulados usando reglas + NLP/ML | Must | F1 |
| RF-AG-02 | Sanitizador redacta con justificación: rule_id, detector, confianza, policy_version | Must | F1 |
| RF-AG-03 | Clasificador asigna nivel de sensibilidad por documento y sección | Must | F1 |
| RF-AG-04 | Auditor registra toda operación crítica de forma inmutable en PostgreSQL | Must | F1 |
| RF-AG-05 | Revisor escala a revisión humana cuando confianza < umbral configurable | Must | F1 |
| RF-AG-06 | Todos los agentes operan sin dependencias de internet | Must | F1 |
| RF-AG-07 | Los agentes soportan políticas hot-reload sin reinicio del servicio | Should | F2 |
| RF-AG-08 | El Detector expone métricas de recall y false positive rate por clase | Must | F2 |

---

## 4. Requisitos no funcionales

### 4.1 Seguridad

| ID | Requisito | Meta Enterprise |
|---|---|---|
| RNF-SEC-01 | Zero Trust: autenticación explícita en cada operación entre componentes | 100% de operaciones inter-componente autenticadas |
| RNF-SEC-02 | Sin secretos estáticos en repositorios ni CI/CD | 0 secretos estáticos |
| RNF-SEC-03 | TLS en todas las comunicaciones internas y externas | 100% |
| RNF-SEC-04 | Row-Level Security en PostgreSQL | Habilitado y auditado |
| RNF-SEC-05 | Cifrado en reposo para artefactos en MinIO (SSE) | 100% de artefactos |
| RNF-SEC-06 | KMS para gestión de claves | Integrado en F4 |
| RNF-SEC-07 | MFA obligatorio para acceso humano | 100% en F4 |

### 4.2 Compliance

| ID | Requisito | Marco |
|---|---|---|
| RNF-COM-01 | Audit trail inmutable con trace_id + artifact_digest + actor + policy_version | GDPR, HIPAA, SOC2 |
| RNF-COM-02 | Exportación de evidencia en formato estándar | GDPR Art. 30, HIPAA |
| RNF-COM-03 | Retención de datos configurable por clase | GDPR, HIPAA |
| RNF-COM-04 | Borrado verificable de datos personales | GDPR Art. 17 |
| RNF-COM-05 | Segregación de funciones con roles auditados | SOC2, HIPAA |
| RNF-COM-06 | SBOM por imagen de contenedor | SLSA, SSDF |
| RNF-COM-07 | Firma de artefactos verificable | SLSA Level 3 |

### 4.3 Disponibilidad y resiliencia

| ID | Requisito | Meta MVP→Producto | Meta Enterprise |
|---|---|---|---|
| RNF-RES-01 | Disponibilidad del servicio de scan | 99% | 99.9% con SLA |
| RNF-RES-02 | RTO ante falla de base de datos | < 1 hora | < 15 min verificado en DR drill |
| RNF-RES-03 | RPO máximo | < 1 hora | < 5 min con WAL archiving |
| RNF-RES-04 | Backup probado | Mensual | Semanal con DR drill trimestral |

### 4.4 Performance

| ID | Requisito | Meta |
|---|---|---|
| RNF-PERF-01 | Latencia p95 de safecontext.scan para documento < 1MB | < 5 segundos |
| RNF-PERF-02 | Latencia p95 de API | < 500ms (excluye procesamiento ML) |
| RNF-PERF-03 | Throughput mínimo sostenido | 100 documentos/hora en single-node |

### 4.5 Operación offline / air-gapped

| ID | Requisito |
|---|---|
| RNF-OFFL-01 | Instalación completa sin acceso a internet |
| RNF-OFFL-02 | Actualización y rollback documentados y probados sin internet |
| RNF-OFFL-03 | Registry privado de imágenes de contenedor |
| RNF-OFFL-04 | Runners/agentes CI/CD self-hosted |
| RNF-OFFL-05 | Modelos NLP/ML descargados y empaquetados localmente |

---

## 5. Restricciones y dependencias

| Restricción | Impacto |
|---|---|
| Redis 8 usa licencia tri-license — requiere revisión legal antes de producción | Puede requerir alternativa (RabbitMQ) si la licencia es incompatible |
| MinIO CE es AGPLv3 — requiere decisión explícita sobre edición | AIStor (comercial) o despliegue AGPL con análisis legal |
| Python 3.12 en security fixes only desde 2025 | Plan de migración a 3.13+ antes de F4 |
| MCP spec puede evolucionar — el servidor debe soportar versionado de tools | Diseño defensivo desde F1 |

---

## 6. Criterios de éxito por fase

| Fase | Criterio binario de éxito |
|---|---|
| F1 | Toda operación de scan genera trace_id + artifact_digest + policy_version. Pipeline gate funcional en GitHub. Despliegue reproducible con Docker Compose. |
| F2 | Restore de base de datos probado y exitoso. Auditoría detallada habilitada con pgAudit. Cache multiinstancia de Next.js consistente. |
| F3 | 100% de imágenes firmadas con Cosign y SBOM adjunto. 0 secretos estáticos en CI. Deploy bloqueado si política o firma falla. |
| F4 | SSO/MFA habilitado. RTO < 15 min verificado en drill. Revisión humana activa para hallazgos críticos. Evidencia exportable para auditoría. |
| F5 | Instalación y actualización completa sin internet. DR drill exitoso en entorno air-gapped. |

---

## 7. Fuera de alcance (explícito)

- SafeContext **no** es un firewall de red ni un WAF.
- SafeContext **no** gestiona el ciclo de vida de modelos de IA (MLOps/LLMOps) — solo gobierna el contexto que les llega.
- SafeContext **no** reemplaza un DLP corporativo — es complementario y especializado en pipelines de IA.
- SafeContext **no** genera respuestas de IA — es un gate de entrada, no un modelo.
- La UI **no** incluye capacidades de edición de documentos — solo visualización, revisión y aprobación.

---

*Derivado de DOC-0 v0.1.0*
*Próxima revisión: antes de iniciar F2*
