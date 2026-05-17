# SafeContext — Glosario Canónico
**Versión**: 0.1.0 · **Fuente de verdad**: DOC-0 §7
**Regla**: ante ambigüedad de significado en cualquier documento del proyecto, este glosario prevalece.

---

| Término | Definición en SafeContext |
|---|---|
| **artifact_digest** | Hash SHA-256 del artefacto procesado. Inmutable. Parte de todo audit trail. Formato: hex string de 64 caracteres. |
| **trace_id** | Identificador de correlación que une todas las operaciones de un flujo completo. Formato UUID v4. Viaja en header `X-Trace-ID` y en body de toda respuesta de operación. |
| **policy_version** | Versión semántica (semver) de la política OPA/Rego activa en el momento de la decisión. Formato: `MAJOR.MINOR.PATCH` (ej. `1.0.0`). |
| **hallazgo** | Resultado de detección: span afectado (start/end), detector que lo identificó, rule_id, nivel de confianza (0.0–1.0) y política aplicada. Representa una instancia de dato sensible detectado. |
| **redaction_map** | Mapa de todas las redacciones aplicadas a un documento: posición (span_start/end), tipo de redacción (mask/remove/replace), justificación y versión de política. Inmutable una vez generado. |
| **gate** | Punto de control que bloquea el flujo hasta que se cumple una condición verificable. No es una advertencia — es un bloqueo con resultado binario (pasa/no pasa). |
| **agente interno** | Componente propio de SafeContext que ejecuta una capacidad especializada localmente. Los agentes internos son: Detector, Sanitizador, Clasificador, Auditor, Revisor. No son integraciones externas. |
| **MCP Server** | Superficie de integración que expone los agentes internos como tools consumibles por agentes LLM. Implementado como módulo de FastAPI. Protocolo: Model Context Protocol (MCP). |
| **sistema de registro** | PostgreSQL — única fuente de verdad para decisiones, auditoría y estado durable. Ningún otro sistema puede ser fuente de verdad. |
| **sistema efímero** | Redis — broker y cache transitorio. Puede perder datos sin impacto en la integridad del negocio. Nunca fuente de verdad. |

---

*Fuente: DOC-0 v0.1.0 §7*
*Actualizar este glosario requiere actualizar también DOC-0.*
