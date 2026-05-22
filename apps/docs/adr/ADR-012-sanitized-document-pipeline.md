# ADR-012 · Documento sanitizado como artefacto del pipeline

**Estado**: Aceptado  
**Fecha**: 2026-05-22  
**Contexto**: Pipeline de detección y redacción de PII/secretos

---

## Contexto

Cuando SafeContext procesa un documento, el `detector_agent` encuentra spans de PII/secretos
y el `sanitizer_agent` registra `Redaction` records en la base de datos. Hasta la sesión
del 2026-05-22, el texto sanitizado solo existía implícitamente — se podía reconstruir
a partir de los redaction records, pero no estaba disponible como un artefacto accesible
para el llamante (UI o MCP agent).

El principal caso de uso del MCP es:

```
Claude Code lee database_config.py
  → llama safecontext.scan(contenido)
  → SafeContext detecta API_KEY y EMAIL
  → Claude Code recibe documento sanitizado (con [REDACTED])
  → Claude Code envía SOLO el documento sanitizado al LLM
```

Sin el documento sanitizado en la respuesta, el MCP no tiene valor real como capa
de gobernanza — el llamante tendría que reconstruirlo manualmente a partir de los spans.

---

## Decisión

**Almacenar `sanitized_text` directamente en el modelo `Operation`** como columna
`Text nullable`, computada y persistida por el `sanitizer_agent`.

**Exponer `sanitized_document`** en `AuditExportResponse` para que los clientes
(UI y MCP) puedan obtenerlo via `GET /v1/audit/{trace_id}`.

---

## Implementación

### sanitizer_agent — `_apply_redactions()`

```python
def _apply_redactions(text, findings, redaction_map) -> str:
    # Procesa spans de FIN a INICIO para preservar offsets
    sorted_findings = sorted(findings, key=lambda f: f.span_start, reverse=True)
    chars = list(text)
    for f in sorted_findings:
        marker = {"mask": "[REDACTED]", "remove": "", "replace": "[REDACTED]"}.get(
            redaction_map.get(f.id, "mask"), "[REDACTED]"
        )
        chars[f.span_start:f.span_end] = list(marker)
    return "".join(chars)
```

El resultado se persiste en `Operation.sanitized_text` junto con los redaction records.

### Deduplicación por `artifact_digest`

Si el mismo documento (mismo SHA256) ya fue procesado con la misma política:
- `GET /v1/scan` retorna el `trace_id` anterior sin re-procesar
- Evita falsos positivos cuando ya-sanitizados se re-escanean

### Whitelist de dominios de prueba en Presidio

Los dominios `@test.com`, `@example.com`, `@localhost` (RFC 2606) y los marcadores
`[REDACTED]` se excluyen del detector para evitar falsos positivos en re-scans.

---

## Consecuencias

**Positivas:**
- El MCP puede retornar el documento sanitizado sin una segunda llamada
- La cadena de gobernanza es completa: detectar → redactar → exponer sanitizado
- Los scans son idempotentes por diseño (dedup por digest)
- Los documentos ya sanitizados no generan nuevos findings (whitelist + [REDACTED] check)

**Negativas / Trade-offs:**
- `sanitized_text` puede ser grande (copia del documento original con mínimos cambios)
- El HMAC del audit export NO incluye `sanitized_text` — solo el contenido original
  preserva la cadena de custodia del `artifact_digest`
- Si el documento es muy largo (> 10MB), considerar almacenar en MinIO como artefacto
  "sanitized" en lugar de en la columna SQL (diferido a F4)

---

## Alternativas consideradas

| Alternativa | Razón de descarte |
|---|---|
| Calcular on-demand en el audit endpoint | Requiere leer el doc de MinIO + aplicar redacciones cada request |
| Almacenar en MinIO como "sanitized" artifact | Más complejo, útil solo para docs muy grandes (diferido a F4) |
| No almacenar, dejar que el cliente reconstruya | El cliente necesita los spans Y el texto original — no es práctico para MCP |
| Retornar sanitized en ScanResponse síncrono | El scan es async — el texto sanitizado no está listo en el momento de la respuesta |

---

## Referencias

- `apps/workers/agents/sanitizer_agent.py` — implementación de `_apply_redactions()`
- `apps/api/db/models/operation.py` — columna `sanitized_text`
- `apps/api/schemas/audit.py` — `AuditExportResponse.sanitized_document`
- `apps/api/db/migrations/versions/0004_operation_sanitized_text_and_digest_index.py`
- ADR-004 — Agentes internos (pipeline de procesamiento)
- ADR-007 — Dramatiq workers (arquitectura async)
