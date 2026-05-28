# SafeContext — Glosario Canónico

**Versión**: 1.0.0 · **Fuente de verdad**: [DOC-PRODUCTO.md](./DOC-PRODUCTO.md)
**Regla**: ante ambigüedad de significado en cualquier documento del proyecto, este glosario prevalece.

---

## Términos del dominio

| Término | Definición en SafeContext |
|---|---|
| **artifact_digest** | Hash SHA-256 del artefacto (documento) procesado. Inmutable. Formato: hex string de 64 caracteres. Parte de todo registro de auditoría. |
| **trace_id** | Identificador de correlación UUID v4 que une todas las operaciones de un flujo de escaneo. Viaja en header `X-Trace-ID` y en body de toda respuesta. Generado por OpenTelemetry. |
| **policy_version** | Versión semántica de la política OPA/Rego activa en el momento de la decisión. Formato: `MAJOR.MINOR.PATCH` (ej. `1.0.0`). Se registra en cada operación para trazabilidad. |
| **hallazgo** *(finding)* | Resultado de detección: span afectado (start/end), detector, rule_id, nivel de confianza (0.0–1.0), severidad y política aplicada. Representa una instancia de dato sensible detectado. |
| **redaction_map** | Mapa de redacciones aplicadas a un documento: posición (span_start/end), tipo (mask/remove/replace), justificación y versión de política. Inmutable una vez generado. |
| **gate** | Punto de control binario (pasa/no pasa) que bloquea un flujo hasta cumplir una condición verificable. No es una advertencia. |
| **operación** *(operation)* | Registro completo de un escaneo: incluye trace_id, actor_id, artifact_digest, status, findings, redactions y chain_hash. Unidad atómica de auditoría. |

## Roles y acceso

| Término | Definición en SafeContext |
|---|---|
| **viewer** | Rol con permisos de solo lectura. Puede enviar escaneos y consultar audit trail. No puede revisar hallazgos ni administrar. |
| **reviewer** | Rol que puede aprobar o rechazar hallazgos escalados. Sujeto a SoD: no puede aprobar sus propios escaneos. |
| **policy_editor** | Rol para gestión de waivers (excepciones de política). Puede crear y revocar waivers con justificación. |
| **admin** | Rol con acceso completo: gestión de tenants, SIEM, retención GDPR, waivers y purga. Máximo nivel de privilegio. |
| **SoD** *(Segregation of Duties)* | Principio de segregación de funciones: quien escanea no puede aprobar los hallazgos de ese mismo escaneo. Implementado en `check_self_approval()`. |

## Agentes internos

| Término | Definición en SafeContext |
|---|---|
| **agente interno** | Componente de SafeContext que ejecuta una capacidad especializada. Son: Detector, Sanitizador, Clasificador, Auditor, Revisor. No son integraciones externas. |
| **detector** | Agente que identifica datos sensibles en texto. Combina spaCy NER, regex (RegexDetector) y diccionarios. Produce hallazgos con confianza 0.0–1.0. |
| **sanitizador** | Agente que redacta (enmascara/elimina/reemplaza) el contenido detectado como sensible. Genera el redaction_map. |
| **clasificador** | Agente que asigna nivel de sensibilidad a secciones de un documento: public, internal, confidential, restricted. |
| **auditor** | Agente que registra cada decisión en el audit trail inmutable con trace_id, artifact_digest, actor y policy_version. |
| **revisor** *(escalation agent)* | Agente que escala hallazgos a revisión humana cuando la confianza está por debajo del umbral o la severidad es critical. |

## Multi-tenancy

| Término | Definición en SafeContext |
|---|---|
| **tenant** | Unidad de aislamiento organizacional. Cada tenant tiene su propia configuración de políticas, quotas, SIEM, retención y cadena de custodia. Aislado por RLS en PostgreSQL. |
| **RLS** *(Row-Level Security)* | Mecanismo de PostgreSQL que restringe el acceso a filas por `tenant_id`. Cada query solo ve datos de su tenant. Migración `0009_rls.py`. |
| **quota** | Límite configurable por tenant: escaneos diarios (`max_scans_per_day`), tamaño de documento (`max_document_size`), requests por minuto (`rate_limit_rpm`). |
| **rate_limit** | Restricción de frecuencia de requests por ventana temporal. Dos niveles: por `client_id` (MCP) y por `tenant_id`. Almacenado en Redis o in-memory. |

## Políticas y excepciones

| Término | Definición en SafeContext |
|---|---|
| **waiver** | Excepción temporal a una regla de detección. Requiere: `rule_id`, `entity_pattern` (regex), justificación (≥20 chars en UI), y opcionalmente `expires_at`. Solo `policy_editor` o `admin` pueden crear/revocar. |
| **OPA** *(Open Policy Agent)* | Motor de evaluación de políticas. Evalúa hallazgos contra reglas Rego para decidir: bloquear, escalar a revisión o permitir. |
| **Rego** | Lenguaje declarativo de políticas usado por OPA. Las políticas SafeContext están en `policies/base/safecontext.rego`. |
| **confidence** | Nivel de certeza del detector sobre un hallazgo, rango 0.0–1.0. Por debajo del umbral configurable → escalado a revisión humana. |
| **severity** | Nivel de impacto de un hallazgo: `low`, `medium`, `high`, `critical`. Determina si se bloquea la operación. Configurable por tenant. |
| **escalado** *(escalation)* | Estado de una operación que requiere aprobación humana. Se activa por: confianza bajo umbral o severidad critical. |

## Cadena de custodia

| Término | Definición en SafeContext |
|---|---|
| **chain_hash** | Hash encadenado SHA-256 para cadena de custodia: `SHA256(prev_chain_hash \|\| operation_hash)`. Per-tenant. Detecta manipulación o eliminación de registros. |
| **digital_signature** | Firma ECDSA-P256 generada por OpenBao Transit sobre la evidencia de auditoría. Clave exportable para verificación offline. |
| **TSA** *(Time Stamping Authority)* | Autoridad externa (RFC 3161) que emite sellos de tiempo para probar que un dato existía en un momento específico. Independiente del reloj del servidor. |
| **WORM** *(Write Once Read Many)* | Almacenamiento inmutable usando MinIO Object Lock en modo GOVERNANCE. Retención predeterminada: 7 años (2555 días). Usado para evidencias y certificados de borrado. |
| **deletion_certificate** | Certificado firmado HMAC-SHA256 que prueba que una purga GDPR fue ejecutada. Incluye: tenant_id, registros eliminados, fecha, motivo. Almacenado en WORM. |

## Integración

| Término | Definición en SafeContext |
|---|---|
| **MCP Server** | Superficie de integración que expone los agentes internos como tools para agentes LLM. Protocolo: Model Context Protocol. Autenticación: OAuth 2.1 + PKCE. |
| **PKCE** *(Proof Key for Code Exchange)* | Extensión de OAuth 2.1 que protege el flujo de autorización contra interceptación. Método: S256. Requerido para clientes MCP. |
| **SIEM** *(Security Information and Event Management)* | Plataforma externa de monitoreo de seguridad. SafeContext emite eventos en formatos CEF, LEEF o JSON via webhook o syslog. Configurable por tenant. |
| **CEF** *(Common Event Format)* | Formato estándar de eventos de seguridad: `CEF:0\|Vendor\|Product\|Version\|EventID\|Name\|Severity\|Extensions`. Usado por Splunk, ArcSight, QRadar. |
| **LEEF** *(Log Event Extended Format)* | Formato de eventos de IBM QRadar. Similar a CEF pero con campos separados por tabulador. |
| **SARIF** *(Static Analysis Results Interchange Format)* | Formato estándar para resultados de análisis estático. SafeContext exporta evidencias en SARIF para integración con GitHub Advanced Security. |

## Infraestructura

| Término | Definición en SafeContext |
|---|---|
| **sistema de registro** | PostgreSQL — única fuente de verdad para decisiones, auditoría y estado durable. Ningún otro sistema puede ser fuente de verdad. |
| **sistema efímero** | Redis — broker y cache transitorio. Puede perder datos sin impacto en integridad. Nunca fuente de verdad. |
| **outbox_pattern** | Patrón de consistencia: operación + evento se persisten en la misma transacción PostgreSQL. El relay lee de la tabla `outbox` y publica en Redis. Garantiza at-least-once delivery. |
| **pgAudit** | Extensión de PostgreSQL que registra operaciones SQL (INSERT, UPDATE, DELETE, DDL) a nivel de base de datos, independiente de la aplicación. |

---

*Fuente canónica: DOC-PRODUCTO.md · Versión 1.0.0 · 2026-05-25*
*Para actualizar este glosario, verificar primero contra el código fuente como fuente de verdad.*
