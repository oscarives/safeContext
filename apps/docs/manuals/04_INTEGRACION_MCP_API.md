# SafeContext — Manual de Integración MCP y API REST
**Versión**: 1.0.0 | **Fecha**: 2026-05-18 | **Audiencia**: Desarrolladores de integración

---

## Tabla de contenidos

1. [Introducción](#1-introducción)
2. [Autenticación](#2-autenticación)
3. [Tools MCP disponibles](#3-tools-mcp-disponibles)
4. [Endpoint versionado /v1/mcp/call](#4-endpoint-versionado-v1mcpcall)
5. [Integración con Claude (Anthropic)](#5-integración-con-claude-anthropic)
6. [Integración con GitHub Actions](#6-integración-con-github-actions)
7. [Integración custom (cualquier agente)](#7-integración-custom-cualquier-agente)
8. [REST API directa](#8-rest-api-directa)
9. [Manejo de errores](#9-manejo-de-errores)
10. [Ejemplos completos](#10-ejemplos-completos)

---

## 1. Introducción

SafeContext expone dos superficies de integración complementarias:

- **MCP Server**: interfaz nativa para agentes LLM y pipelines CI/CD. Implementa el protocolo [Model Context Protocol (MCP)](https://modelcontextprotocol.io). Un único endpoint (`POST /v1/mcp/call`) despacha los 6 tools disponibles.
- **REST API directa**: endpoints HTTP convencionales para integraciones que no usan el protocolo MCP o que necesitan acceso granular a recursos específicos (audit trail, revisión humana, health).

### Cuándo usar MCP vs REST directamente

| Caso de uso | Superficie recomendada |
|---|---|
| Agente LLM (Claude, Codex, etc.) consumiendo SafeContext como tool | MCP Server |
| Pipeline CI/CD bloqueando en hallazgos | MCP Server (via GitHub Action) o REST |
| Consultar audit trail de una operación específica | REST: `GET /v1/audit/{trace_id}` |
| Dashboard de revisión humana | REST: `GET /v1/review/pending` |
| Health check desde load balancer | REST: `GET /health` |
| Integración custom sin SDK MCP | MCP Server via HTTP simple o REST |

### URL base

```
http://safecontext-host:8000
```

En producción con TLS:
```
https://safecontext.tu-dominio.com
```

La documentación OpenAPI interactiva está disponible en:
```
http://safecontext-host:8000/docs
```

---

## 2. Autenticación

### Bearer token

Todos los endpoints requieren autenticación via Bearer token en el header `Authorization`:

```
Authorization: Bearer <token>
```

### Cómo obtener el token

En desarrollo (F1-F2), el token se configura directamente en el archivo `.env` del servidor:

```bash
# .env del servidor SafeContext
MCP_AUTH_TOKEN=sc_dev_a1b2c3d4e5f6...   # token de desarrollo
```

El cliente usa ese mismo valor en sus requests. En producción (F3+), el token se obtiene via OAuth2 client credentials flow contra Keycloak:

```bash
# Obtener token via OAuth2 client credentials
curl -s -X POST https://keycloak.tu-dominio.com/realms/safecontext/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=mi-agente-id" \
  -d "client_secret=${CLIENT_SECRET}" \
  | jq -r '.access_token'
```

```python
# Python: obtener token con caché automático
import httpx
import time

class SafeContextAuth:
    def __init__(self, token_url: str, client_id: str, client_secret: str):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._expires_at = 0

    def get_token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        resp = httpx.post(self.token_url, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"]
        return self._token
```

### Rate limiting

SafeContext aplica rate limiting en dos capas:

**Capa API** (por `client_id`):
- **Limite**: 100 requests por minuto por `client_id`
- **Header requerido**: `X-Client-ID: <identificador-de-tu-cliente>`
- **Respuesta al superar el limite**: `429 Too Many Requests` con header `Retry-After: <segundos>`

**Capa Ingress/K8s** (por IP):
- **Limite**: 50 requests por segundo por IP de origen
- **Burst**: x3 (150 requests en rafaga)
- **Conexiones concurrentes**: max 20 por IP

```
X-Client-ID: github-actions-prod
X-Client-ID: claude-agent-prod
X-Client-ID: mi-pipeline-staging
```

### Respuestas de error de autenticación

```json
// 401 Unauthorized — sin token o token inválido
{
  "error": "unauthorized",
  "message": "Missing or invalid Bearer token",
  "trace_id": null
}

// 429 Too Many Requests — rate limit superado
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit of 100 RPM exceeded for client_id 'my-agent'",
  "retry_after": 23
}
```

---

## 3. Tools MCP disponibles

Todos los tools se invocan con el mismo endpoint:

```
POST /v1/mcp/call
Authorization: Bearer <token>
X-Client-ID: <client-id>
Content-Type: application/json
```

### 3.1 safecontext.scan

Escanea un documento en busca de PII, secretos y datos sensibles. Retorna hallazgos con justificación completa.

**Request:**

```json
{
  "tool": "safecontext.scan",
  "tool_version": "1.0.0",
  "input": {
    "document": "Hola, soy Juan García y mi email es juan.garcia@empresa.com. La clave de API es sk-prod-a1b2c3d4e5f6g7h8i9j0.",
    "document_encoding": "text",
    "policy_name": "base",
    "policy_version": "1.0.0"
  }
}
```

**Ejemplo curl:**

```bash
curl -s -X POST http://safecontext-host:8000/v1/mcp/call \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "X-Client-ID: mi-agente" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "safecontext.scan",
    "input": {
      "document": "Hola, soy Juan García y mi email es juan.garcia@empresa.com. La clave de API es sk-prod-a1b2c3d4e5f6g7h8i9j0.",
      "policy_name": "base"
    }
  }' | jq
```

**Ejemplo Python:**

```python
import httpx

SAFECONTEXT_URL = "http://safecontext-host:8000"
TOKEN = "sc_dev_a1b2c3d4e5f6..."

def scan_document(document: str, policy_name: str = "base") -> dict:
    resp = httpx.post(
        f"{SAFECONTEXT_URL}/v1/mcp/call",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Client-ID": "mi-python-app",
        },
        json={
            "tool": "safecontext.scan",
            "input": {
                "document": document,
                "policy_name": policy_name,
            },
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

result = scan_document("Mi tarjeta de crédito es 4111 1111 1111 1111.")
print(result)
```

**Response de ejemplo:**

```json
{
  "tool": "safecontext.scan",
  "tool_version": "1.0.0",
  "trace_id": "550e8400-e29b-41d4-a716-446655440001",
  "content": {
    "trace_id": "550e8400-e29b-41d4-a716-446655440001",
    "artifact_digest": "a3f5d2e1b8c7f9a2d4e6b3c8f1a9d5e2b7c4f0a3e8d6b1c9f2a7d4e0b5c3f8",
    "policy_version": "1.0.0",
    "status": "completed",
    "requires_human_review": false,
    "findings": [
      {
        "id": "7f8e9d2c-3b4a-5c6d-7e8f-9a0b1c2d3e4f",
        "detector": "presidio.PERSON",
        "rule_id": "PERSON_NLP_001",
        "span_start": 10,
        "span_end": 21,
        "confidence": 0.92,
        "severity": "medium",
        "explanation": {
          "entity_type": "PERSON",
          "context_before": "Hola, soy ",
          "matched_length": 11,
          "model": "es_core_news_lg"
        }
      },
      {
        "id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        "detector": "presidio.EMAIL_ADDRESS",
        "rule_id": "EMAIL_REGEX_001",
        "span_start": 36,
        "span_end": 62,
        "confidence": 0.99,
        "severity": "medium",
        "explanation": {
          "entity_type": "EMAIL_ADDRESS",
          "context_before": "mi email es ",
          "matched_length": 26,
          "model": "regex"
        }
      },
      {
        "id": "9b8a7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d",
        "detector": "presidio.API_KEY",
        "rule_id": "API_KEY_PATTERN_001",
        "span_start": 82,
        "span_end": 102,
        "confidence": 0.97,
        "severity": "critical",
        "explanation": {
          "entity_type": "API_KEY",
          "context_before": "clave de API es ",
          "matched_length": 20,
          "pattern": "sk-[a-z]+-[a-z0-9]{16}"
        }
      }
    ]
  }
}
```

**Campos del response:**

| Campo | Tipo | Descripción |
|---|---|---|
| `trace_id` | UUID | Identificador del flujo. Usar para sanitizar, auditar y consultar estado |
| `artifact_digest` | string | SHA-256 del documento escaneado |
| `policy_version` | string | Versión de la política OPA usada en el scan |
| `requires_human_review` | boolean | `true` si algún hallazgo supera el umbral de escalación |
| `findings[].detector` | string | Detector que identificó el hallazgo |
| `findings[].confidence` | float | Probabilidad 0.0–1.0 |
| `findings[].severity` | string | `low` / `medium` / `high` / `critical` |
| `findings[].span_start` | int | Offset de inicio en bytes (UTF-8) |
| `findings[].span_end` | int | Offset de fin en bytes (UTF-8) |

### 3.2 safecontext.sanitize

Sanitiza el documento del `trace_id` indicado, aplicando redacciones sobre los hallazgos del scan previo.

**Request:**

```json
{
  "tool": "safecontext.sanitize",
  "input": {
    "trace_id": "550e8400-e29b-41d4-a716-446655440001",
    "redaction_type": "mask",
    "replacement_token": "[REDACTED]"
  }
}
```

Valores de `redaction_type`:
- `mask`: reemplaza con `[ENTITY_TYPE]`, e.g. `[EMAIL_ADDRESS]`
- `remove`: elimina el contenido detectado (deja un espacio en blanco)
- `replace`: reemplaza con el valor de `replacement_token`

**Ejemplo curl:**

```bash
curl -s -X POST http://safecontext-host:8000/v1/mcp/call \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "X-Client-ID: mi-agente" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "safecontext.sanitize",
    "input": {
      "trace_id": "550e8400-e29b-41d4-a716-446655440001",
      "redaction_type": "mask"
    }
  }' | jq
```

**Ejemplo Python:**

```python
def sanitize_document(trace_id: str, redaction_type: str = "mask") -> dict:
    resp = httpx.post(
        f"{SAFECONTEXT_URL}/v1/mcp/call",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Client-ID": "mi-python-app",
        },
        json={
            "tool": "safecontext.sanitize",
            "input": {
                "trace_id": trace_id,
                "redaction_type": redaction_type,
            },
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

sanitized = sanitize_document("550e8400-e29b-41d4-a716-446655440001")
print(sanitized["content"]["sanitized_document"])
```

**Response de ejemplo:**

```json
{
  "tool": "safecontext.sanitize",
  "tool_version": "1.0.0",
  "trace_id": "550e8400-e29b-41d4-a716-446655440001",
  "content": {
    "trace_id": "550e8400-e29b-41d4-a716-446655440001",
    "sanitized_document": "Hola, soy [PERSON] y mi email es [EMAIL_ADDRESS]. La clave de API es [API_KEY].",
    "sanitized_artifact_digest": "b4c6d8e2f0a3b5d7e9c1f3a5b7d9e1c3f5a7b9d1e3c5f7a9b1d3e5c7f9a1b3d5",
    "policy_version": "1.0.0",
    "redaction_map": [
      {
        "finding_id": "7f8e9d2c-3b4a-5c6d-7e8f-9a0b1c2d3e4f",
        "span_start": 10,
        "span_end": 21,
        "redaction_type": "mask",
        "replacement": "[PERSON]",
        "policy_version": "1.0.0"
      },
      {
        "finding_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        "span_start": 36,
        "span_end": 62,
        "redaction_type": "mask",
        "replacement": "[EMAIL_ADDRESS]",
        "policy_version": "1.0.0"
      },
      {
        "finding_id": "9b8a7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d",
        "span_start": 82,
        "span_end": 102,
        "redaction_type": "mask",
        "replacement": "[API_KEY]",
        "policy_version": "1.0.0"
      }
    ]
  }
}
```

### 3.3 safecontext.classify

Clasifica el nivel de sensibilidad de un documento por sección.

**Request:**

```json
{
  "tool": "safecontext.classify",
  "input": {
    "document": "## Resumen ejecutivo\nEsta es información pública del producto.\n\n## Arquitectura interna\nEl sistema usa PostgreSQL 18.4 con RLS habilitado para tenant isolation."
  }
}
```

**Ejemplo curl:**

```bash
curl -s -X POST http://safecontext-host:8000/v1/mcp/call \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "X-Client-ID: mi-agente" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "safecontext.classify",
    "input": {
      "document": "## Resumen ejecutivo\nEsta es información pública.\n\n## Secretos de producción\nDB_PASSWORD=s3cr3t123"
    }
  }' | jq
```

**Response de ejemplo:**

```json
{
  "tool": "safecontext.classify",
  "tool_version": "1.0.0",
  "trace_id": "660f9500-f30c-52e5-b827-557766551112",
  "content": {
    "trace_id": "660f9500-f30c-52e5-b827-557766551112",
    "overall_level": "restricted",
    "policy_version": "1.0.0",
    "sections": [
      {
        "section_id": 1,
        "heading": "Resumen ejecutivo",
        "level": "public",
        "justification": "No se detectaron entidades sensibles. Contenido descriptivo genérico."
      },
      {
        "section_id": 2,
        "heading": "Secretos de producción",
        "level": "restricted",
        "justification": "Contiene hallazgo API_KEY/PASSWORD con confidence=0.97. Nivel escalado a 'restricted' por política base."
      }
    ]
  }
}
```

**Niveles de clasificación:**

| Nivel | Descripción | Acción recomendada |
|---|---|---|
| `public` | Sin datos sensibles detectados | Puede usarse sin restricciones |
| `internal` | Datos internos de la organización | Usar solo en sistemas internos |
| `confidential` | PII, datos de clientes, datos regulados | Requiere sanitización antes de enviar a IA |
| `restricted` | Secretos, credenciales, datos críticos | Bloquear; no enviar a ningún modelo externo |

### 3.4 safecontext.audit

Recupera la evidencia completa de una operación dado su `trace_id`. Incluye la operación, hallazgos, redacciones, artefactos y HMAC de integridad.

**Request:**

```json
{
  "tool": "safecontext.audit",
  "input": {
    "trace_id": "550e8400-e29b-41d4-a716-446655440001"
  }
}
```

**Ejemplo curl:**

```bash
curl -s -X POST http://safecontext-host:8000/v1/mcp/call \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "X-Client-ID: compliance-tool" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "safecontext.audit",
    "input": {"trace_id": "550e8400-e29b-41d4-a716-446655440001"}
  }' | jq
```

**Response de ejemplo:**

```json
{
  "tool": "safecontext.audit",
  "tool_version": "1.0.0",
  "trace_id": "550e8400-e29b-41d4-a716-446655440001",
  "content": {
    "trace_id": "550e8400-e29b-41d4-a716-446655440001",
    "operation": {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "actor_id": "claude-agent-prod",
      "actor_type": "mcp_agent",
      "artifact_digest": "a3f5d2e1b8c7f9a2d4e6b3c8f1a9d5e2b7c4f0a3e8d6b1c9f2a7d4e0b5c3f8",
      "policy_version": "1.0.0",
      "status": "completed",
      "created_at": "2026-05-18T10:23:45.123Z",
      "completed_at": "2026-05-18T10:23:47.456Z"
    },
    "findings_count": 3,
    "redactions_count": 3,
    "artifacts": [
      {
        "artifact_type": "sanitized",
        "minio_key": "safecontext-artifacts/sanitized/a1b2c3d4/sanitized.txt",
        "digest": "b4c6d8e2f0a3b5d7e9c1f3a5b7d9e1c3f5a7b9d1e3c5f7a9b1d3e5c7f9a1b3d5",
        "worm_locked": true,
        "created_at": "2026-05-18T10:23:47.300Z"
      }
    ],
    "evidence_hmac": "sha256=7d3f1c9a2b4e6f8d0a2c4e6f8d0a2c4e6f8d0a2c4e6f8d0a2c4e6f8d0a2c4e6",
    "evidence_hmac_algorithm": "HMAC-SHA256"
  }
}
```

El campo `evidence_hmac` permite verificar la integridad del audit trail. El HMAC se calcula sobre `trace_id + artifact_digest + policy_version + findings_count + completed_at` usando la clave HMAC del servidor.

### 3.5 safecontext.policy.get

Recupera la definición de una política OPA activa.

**Request:**

```json
{
  "tool": "safecontext.policy.get",
  "input": {
    "policy_name": "base",
    "policy_version": "1.0.0"
  }
}
```

**Ejemplo curl:**

```bash
curl -s -X POST http://safecontext-host:8000/v1/mcp/call \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "X-Client-ID: policy-inspector" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "safecontext.policy.get",
    "input": {"policy_name": "base"}
  }' | jq
```

**Response de ejemplo:**

```json
{
  "tool": "safecontext.policy.get",
  "tool_version": "1.0.0",
  "content": {
    "policy_name": "base",
    "policy_version": "1.0.0",
    "description": "SafeContext base policy — applies to all document types unless overridden",
    "entity_classes": [
      {"class": "EMAIL_ADDRESS", "confidence_threshold": 0.85, "base_severity": "medium"},
      {"class": "API_KEY",       "confidence_threshold": 0.95, "base_severity": "critical"},
      {"class": "PASSWORD",      "confidence_threshold": 0.95, "base_severity": "critical"},
      {"class": "SSN",           "confidence_threshold": 0.85, "base_severity": "critical"},
      {"class": "CREDIT_CARD",   "confidence_threshold": 0.90, "base_severity": "high"},
      {"class": "PERSON",        "confidence_threshold": 0.85, "base_severity": "medium"},
      {"class": "PHONE_NUMBER",  "confidence_threshold": 0.80, "base_severity": "medium"},
      {"class": "IBAN_CODE",     "confidence_threshold": 0.85, "base_severity": "high"},
      {"class": "MEDICAL_RECORD","confidence_threshold": 0.85, "base_severity": "critical"},
      {"class": "IP_ADDRESS",    "confidence_threshold": 0.75, "base_severity": "low"}
    ],
    "rules_summary": {
      "requires_review": "confidence < threshold OR severity == critical",
      "should_block": "any critical finding above threshold",
      "operation_requires_review": "any finding requires_review"
    },
    "rego_source_url": "/v1/policy/base/1.0.0/source",
    "updated_at": "2026-05-18T08:00:00Z"
  }
}
```

### 3.6 safecontext.approve (v1.1.0)

Permite a un agente con permisos delegados aprobar o rechazar un hallazgo escalado, sin requerir acción humana en la UI. Disponible desde la versión `1.1.0` del MCP Server.

**Cuándo usar**: cuando un agente de revisión automatizada (con permisos explícitos de `reviewer` en su `client_id`) procesa hallazgos de bajo impacto que cumplen criterios predefinidos para aprobación automática delegada.

**Request:**

```json
{
  "tool": "safecontext.approve",
  "tool_version": "1.1.0",
  "input": {
    "finding_id": "7f8e9d2c-3b4a-5c6d-7e8f-9a0b1c2d3e4f",
    "decision": "approve",
    "justification": "Hallazgo PERSON con confianza 0.92 en documento de prueba no-producción. Aprobado automáticamente por política de entorno dev."
  }
}
```

Valores de `decision`: `approve` o `reject`.

**Response de ejemplo:**

```json
{
  "tool": "safecontext.approve",
  "tool_version": "1.1.0",
  "content": {
    "finding_id": "7f8e9d2c-3b4a-5c6d-7e8f-9a0b1c2d3e4f",
    "decision": "approve",
    "approval_trace_id": "770a0611-g41d-63f6-c938-668877662223",
    "approved_by_agent_id": "automated-reviewer-prod",
    "approved_at": "2026-05-18T10:30:00Z"
  }
}
```

**Nota de seguridad**: este tool requiere que el `client_id` del agente tenga el scope `safecontext:approve` asignado explícitamente en Keycloak. Un agente de scan normal con scope `safecontext:scan` no puede invocar este tool (retorna `403 Forbidden`).

---

## 4. Endpoint versionado /v1/mcp/call

### Cómo usar tool_version para fijar versión

El campo `tool_version` en el request body permite fijar la versión del tool exacta:

```json
{
  "tool": "safecontext.scan",
  "tool_version": "1.0.0",
  "input": { ... }
}
```

Si se omite `tool_version`, SafeContext usa la versión más reciente disponible del tool. Para integraciones en producción, **se recomienda siempre fijar la versión** para evitar cambios de comportamiento inesperados.

### Backward compatibility N-1

SafeContext garantiza compatibilidad con la versión N-1 de cada tool. Cuando se publica la versión 1.1.0 de `safecontext.approve`, la versión 1.0.0 de todos los demás tools sigue siendo funcional sin cambios.

Las versiones deprecadas se anuncian con un mínimo de 60 días de antelación en el header de respuesta:

```
X-SafeContext-Deprecation: tool=safecontext.scan version=1.0.0 sunset=2026-08-01
```

### Ejemplo de upgrade de 1.0.0 a 1.1.0

Escenario: tu integración usa `safecontext.scan@1.0.0` y quieres adoptar `safecontext.approve@1.1.0` sin modificar los otros tools.

**Antes:**
```python
# Solo scan — sin approve
response = client.call_tool("safecontext.scan", tool_version="1.0.0", input=input_data)
```

**Después:**
```python
# scan sigue en 1.0.0; approve usa 1.1.0
scan_response = client.call_tool("safecontext.scan", tool_version="1.0.0", input=scan_input)

if scan_response["content"]["requires_human_review"]:
    # Nueva capacidad de aprobación delegada
    approve_response = client.call_tool(
        "safecontext.approve",
        tool_version="1.1.0",
        input={
            "finding_id": scan_response["content"]["findings"][0]["id"],
            "decision": "approve",
            "justification": "Aprobación automática para entorno dev",
        }
    )
```

Los tools con versiones distintas coexisten sin conflicto. No hay necesidad de migrar todos los tools al mismo tiempo.

### Descubrir tools disponibles

```bash
# Listar todos los tools y versiones disponibles
curl -s http://safecontext-host:8000/v1/mcp/tools \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" | jq

# Response
{
  "tools": [
    {"name": "safecontext.scan",       "versions": ["1.0.0"], "latest": "1.0.0"},
    {"name": "safecontext.sanitize",   "versions": ["1.0.0"], "latest": "1.0.0"},
    {"name": "safecontext.classify",   "versions": ["1.0.0"], "latest": "1.0.0"},
    {"name": "safecontext.audit",      "versions": ["1.0.0"], "latest": "1.0.0"},
    {"name": "safecontext.policy.get", "versions": ["1.0.0"], "latest": "1.0.0"},
    {"name": "safecontext.approve",    "versions": ["1.1.0"], "latest": "1.1.0"}
  ]
}
```

---

## 5. Integración con Claude (Anthropic)

Claude puede usar SafeContext como MCP tool nativo. El siguiente ejemplo muestra cómo configurar Claude para que valide el contexto antes de procesarlo con el Anthropic SDK.

```python
import anthropic
import httpx
import os

SAFECONTEXT_URL = os.environ["SAFECONTEXT_URL"]        # http://safecontext-host:8000
SAFECONTEXT_TOKEN = os.environ["SAFECONTEXT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

class SafeContextClient:
    """Cliente liviano para SafeContext MCP."""

    def __init__(self, base_url: str, token: str, client_id: str = "claude-integration"):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "X-Client-ID": client_id,
            "Content-Type": "application/json",
        }

    def call_tool(self, tool: str, input_data: dict, tool_version: str = None) -> dict:
        payload = {"tool": tool, "input": input_data}
        if tool_version:
            payload["tool_version"] = tool_version
        resp = httpx.post(f"{self.base_url}/v1/mcp/call", headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def scan_and_sanitize(self, document: str, policy: str = "base") -> tuple[str, str]:
        """Escanea y sanitiza un documento. Retorna (doc_sanitizado, trace_id)."""
        scan = self.call_tool("safecontext.scan", {"document": document, "policy_name": policy})
        content = scan["content"]
        trace_id = content["trace_id"]

        if content["requires_human_review"]:
            raise ValueError(
                f"Document requires human review before processing. "
                f"trace_id={trace_id}. "
                f"Visit http://safecontext-host:8000 to review."
            )

        if not content["findings"]:
            return document, trace_id  # sin hallazgos, documento limpio

        sanitized = self.call_tool("safecontext.sanitize", {
            "trace_id": trace_id,
            "redaction_type": "mask",
        })
        return sanitized["content"]["sanitized_document"], trace_id


def process_document_with_claude(raw_document: str, user_question: str) -> str:
    """
    Flujo completo: validar con SafeContext antes de enviar a Claude.
    Garantiza que Claude nunca recibe datos sensibles sin sanitizar.
    """
    sc = SafeContextClient(SAFECONTEXT_URL, SAFECONTEXT_TOKEN)

    # 1. Sanitizar antes de enviar a Claude
    safe_document, trace_id = sc.scan_and_sanitize(raw_document)
    print(f"[SafeContext] Documento sanitizado. trace_id={trace_id}")

    # 2. Enviar documento sanitizado a Claude
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"Documento (sanitizado):\n\n{safe_document}\n\nPregunta: {user_question}"
            }
        ],
        system=(
            "Eres un asistente que analiza documentos. "
            "El documento ya fue sanitizado por SafeContext (trace_id: " + trace_id + "). "
            "Cualquier dato entre corchetes como [EMAIL_ADDRESS] o [API_KEY] es información redactada."
        ),
    )
    return message.content[0].text


# Uso
respuesta = process_document_with_claude(
    raw_document="El cliente Juan García (juan@ejemplo.com) necesita soporte. Token: sk-prod-abc123.",
    user_question="¿Cuál es el motivo del contacto del cliente?"
)
print(respuesta)
# → "El cliente necesita soporte técnico. [Los datos de identificación han sido sanitizados]"
```

---

## 6. Integración con GitHub Actions

### YAML completo del workflow

```yaml
# .github/workflows/security-gate.yml
name: SafeContext Security Gate

on:
  push:
    branches: [main, develop]
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write   # necesario para post-comment: true

jobs:
  safecontext-scan:
    name: Security Gate — SafeContext
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: SafeContext Security Gate
        id: sc-gate
        uses: safecontext/action@v1
        with:
          api-url: ${{ secrets.SAFECONTEXT_API_URL }}
          token: ${{ secrets.SAFECONTEXT_TOKEN }}
          document-path: "."
          policy-name: "base"
          fail-on-severity: "high"
          post-comment: "true"

      - name: Print scan summary
        run: |
          echo "SafeContext result: ${{ steps.sc-gate.outputs.result }}"
          echo "Findings count: ${{ steps.sc-gate.outputs.findings-count }}"
          echo "Trace ID: ${{ steps.sc-gate.outputs.trace-id }}"

      # El paso siguiente solo corre si el scan pasó (exit 0)
      - name: Continue with build
        if: steps.sc-gate.outputs.result == 'pass'
        run: echo "Document is clean — proceeding with build"
```

### Cómo configurar los secrets

```bash
# En la configuración del repositorio GitHub:
# Settings → Secrets and variables → Actions → New repository secret

# SAFECONTEXT_API_URL = https://safecontext.tu-dominio.com
# SAFECONTEXT_TOKEN   = sc_prod_xxxxxx...
```

### Cómo interpretar pass/block

| Output `result` | Exit code | Significado | Acción del pipeline |
|---|---|---|---|
| `pass` | `0` | Sin hallazgos en o por encima de `fail-on-severity` | Pipeline continúa |
| `block` | `1` | Hallazgos críticos detectados | Pipeline bloqueado; se crea PR comment |

### Cómo ver el comment en el PR

Cuando `post-comment: true` y hay hallazgos, la acción crea automáticamente un comment en el PR:

```markdown
## SafeContext Security Gate — BLOCKED

**trace_id**: `550e8400-e29b-41d4-a716-446655440001`
**policy**: base v1.0.0
**findings**: 2 hallazgos (1 critical, 1 high)

| # | Tipo | Severidad | Confianza | Archivo |
|---|---|---|---|---|
| 1 | API_KEY | critical | 0.97 | src/config.py:45 |
| 2 | EMAIL_ADDRESS | medium | 0.99 | docs/example.md:12 |

Para ver la evidencia completa:
`GET https://safecontext.tu-dominio.com/v1/audit/550e8400-e29b-41d4-a716-446655440001`

[Ver en SafeContext UI](https://safecontext.tu-dominio.com/operations/550e8400...)
```

### Workflow avanzado con múltiples entornos

```yaml
# Escaneo diferenciado por entorno
safecontext-scan:
  strategy:
    matrix:
      env: [staging, production]
      include:
        - env: staging
          policy: base
          fail-on-severity: high
        - env: production
          policy: hipaa       # política más estricta para producción
          fail-on-severity: medium

  steps:
    - uses: actions/checkout@v4
    - uses: safecontext/action@v1
      with:
        api-url: ${{ secrets.SAFECONTEXT_API_URL }}
        token: ${{ secrets.SAFECONTEXT_TOKEN }}
        policy-name: ${{ matrix.policy }}
        fail-on-severity: ${{ matrix.fail-on-severity }}
```

---

## 7. Integración custom (cualquier agente)

Esta sección muestra cómo integrar SafeContext desde cualquier agente o aplicación Python sin usar el SDK de Anthropic ni la GitHub Action.

### Patrón recomendado

```
scan(document)
    │
    ├── si requires_human_review == true:
    │       Esperar aprobación humana (polling o webhook)
    │
    └── si requires_human_review == false:
            sanitize(trace_id)
                │
                └── Usar documento sanitizado
```

### Implementación completa en Python

```python
"""
Integración SafeContext — Python puro, sin SDKs especiales.
Compatible con cualquier agente o sistema.
"""

import time
import httpx
import os
from typing import Optional


class SafeContextError(Exception):
    pass


class HumanReviewRequired(SafeContextError):
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        super().__init__(f"Human review required for trace_id={trace_id}")


class SafeContext:
    def __init__(
        self,
        base_url: str,
        token: str,
        client_id: str,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self._headers = {
            "Authorization": f"Bearer {token}",
            "X-Client-ID": client_id,
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def _call(self, tool: str, input_data: dict, tool_version: Optional[str] = None) -> dict:
        payload = {"tool": tool, "input": input_data}
        if tool_version:
            payload["tool_version"] = tool_version

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self.base_url}/v1/mcp/call",
                headers=self._headers,
                json=payload,
            )

        if resp.status_code == 401:
            raise SafeContextError("Authentication failed. Check your Bearer token.")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "60")
            raise SafeContextError(f"Rate limit exceeded. Retry after {retry_after}s.")
        resp.raise_for_status()
        return resp.json()

    def scan(self, document: str, policy_name: str = "base") -> dict:
        """Escanea el documento. Retorna el resultado completo con findings."""
        return self._call("safecontext.scan", {
            "document": document,
            "policy_name": policy_name,
        })

    def sanitize(self, trace_id: str, redaction_type: str = "mask") -> dict:
        """Sanitiza el documento de la operación indicada por trace_id."""
        return self._call("safecontext.sanitize", {
            "trace_id": trace_id,
            "redaction_type": redaction_type,
        })

    def classify(self, document: str) -> dict:
        """Clasifica el nivel de sensibilidad del documento."""
        return self._call("safecontext.classify", {"document": document})

    def audit(self, trace_id: str) -> dict:
        """Recupera la evidencia completa de la operación."""
        return self._call("safecontext.audit", {"trace_id": trace_id})

    def get_operation_status(self, trace_id: str) -> str:
        """Consulta el estado actual de una operación via REST API."""
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                f"{self.base_url}/v1/scan/{trace_id}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()["status"]

    def scan_and_sanitize(
        self,
        document: str,
        policy_name: str = "base",
        redaction_type: str = "mask",
        wait_for_review: bool = False,
        poll_interval: float = 2.0,
        max_wait: float = 300.0,
    ) -> tuple[str, str]:
        """
        Flujo completo: scan → [esperar revisión si necesario] → sanitize.

        Returns:
            tuple(safe_document, trace_id)

        Raises:
            HumanReviewRequired: si requires_human_review y wait_for_review=False
        """
        scan_result = self.scan(document, policy_name)
        content = scan_result["content"]
        trace_id = content["trace_id"]

        if not content["findings"]:
            return document, trace_id  # documento limpio

        if content["requires_human_review"]:
            if not wait_for_review:
                raise HumanReviewRequired(trace_id)

            # Esperar hasta que la revisión humana complete
            elapsed = 0.0
            while elapsed < max_wait:
                status = self.get_operation_status(trace_id)
                if status == "sanitize_pending":
                    break
                if status in ("rejected", "failed"):
                    raise SafeContextError(f"Operation {trace_id} was {status}")
                time.sleep(poll_interval)
                elapsed += poll_interval
            else:
                raise SafeContextError(f"Timeout waiting for human review of {trace_id}")

        sanitize_result = self.sanitize(trace_id, redaction_type)
        return sanitize_result["content"]["sanitized_document"], trace_id


# ---- Uso ----

sc = SafeContext(
    base_url=os.environ["SAFECONTEXT_URL"],
    token=os.environ["SAFECONTEXT_TOKEN"],
    client_id="my-custom-agent-v1",
)

# Caso 1: scan simple
raw_doc = "Contactar a María López en maria.lopez@empresa.com, tel: +34 612 345 678"

try:
    clean_doc, trace_id = sc.scan_and_sanitize(raw_doc)
    print(f"Documento sanitizado: {clean_doc}")
    print(f"Audit trail: {trace_id}")
    # → "Contactar a [PERSON] en [EMAIL_ADDRESS], tel: [PHONE_NUMBER]"

except HumanReviewRequired as e:
    print(f"Requiere revisión humana. Visitar UI con trace_id={e.trace_id}")

# Caso 2: esperar revisión humana automáticamente
clean_doc, trace_id = sc.scan_and_sanitize(
    raw_doc,
    wait_for_review=True,
    poll_interval=5.0,
    max_wait=600.0,
)
```

---

## 8. REST API directa

Además del endpoint MCP, SafeContext expone los siguientes endpoints REST convencionales:

### Limites de documentos

| Constraint | Valor | Error si se excede |
|---|---|---|
| Tamano maximo de documento | 10 MB (10,485,760 bytes) | `422 Unprocessable Entity` |

### POST /v1/scan

Inicia una operacion de scan directamente sin pasar por el dispatcher MCP.

```bash
curl -s -X POST http://safecontext-host:8000/v1/scan \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "X-Client-ID: my-app" \
  -H "Content-Type: application/json" \
  -d '{
    "document": "Mi contraseña es P@ssw0rd123",
    "policy_name": "base"
  }'

# Response: 202 Accepted
{
  "trace_id": "880b0733-h52e-74g7-d049-779988773334",
  "status": "pending",
  "message": "Scan initiated"
}
```

### GET /health

Verifica el estado de todos los componentes. Usado por load balancers y orquestadores.

```bash
curl -s http://safecontext-host:8000/health | jq

# Response: 200 OK (sistema saludable)
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "postgresql": {"status": "healthy", "latency_ms": 2},
    "redis":      {"status": "healthy", "latency_ms": 1},
    "minio":      {"status": "healthy", "latency_ms": 5},
    "broker":     {"status": "healthy", "latency_ms": 1}
  },
  "timestamp": "2026-05-18T10:30:00Z"
}

# Response: 503 Service Unavailable (componente degradado)
{
  "status": "degraded",
  "components": {
    "postgresql": {"status": "healthy", "latency_ms": 2},
    "redis":      {"status": "unhealthy", "error": "connection refused"},
    "minio":      {"status": "healthy", "latency_ms": 5},
    "broker":     {"status": "healthy", "latency_ms": 1}
  }
}
```

### GET /v1/review/pending

Lista operaciones escaladas que requieren revision humana. Solo accesible para el rol `Reviewer` o superior.

**Parametros de paginacion**:
| Parametro | Tipo | Default | Rango |
|---|---|---|---|
| `limit` | int | 20 | 1–100 |
| `offset` | int | 0 | >= 0 |

```bash
curl -s "http://safecontext-host:8000/v1/review/pending?limit=20&offset=0" \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" | jq

# Response
{
  "pending": [
    {
      "operation_id": "a1b2c3d4-...",
      "trace_id": "550e8400-...",
      "actor_type": "mcp_agent",
      "escalated_at": "2026-05-18T10:25:00Z",
      "findings_summary": {"critical": 1, "high": 0, "medium": 2, "low": 0}
    }
  ],
  "total": 1
}
```

> **Nota de seguridad**: Un reviewer no puede aprobar operaciones donde el `actor_id` coincide con su propio JWT `sub` (segregation of duties). Intentarlo retorna `403 Forbidden`.

### POST /v1/review/{id}/approve

Aprueba una operación escalada. Requiere rol `Reviewer`.

```bash
curl -s -X POST "http://safecontext-host:8000/v1/review/a1b2c3d4-.../approve" \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "justification": "Revisado manualmente. Datos de prueba — aprobado para sanitización."
  }'
```

### POST /v1/review/{id}/reject

Rechaza una operación escalada. El documento no será sanitizado.

```bash
curl -s -X POST "http://safecontext-host:8000/v1/review/a1b2c3d4-.../reject" \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "justification": "Contiene credenciales reales de producción. No procesar."
  }'
```

### POST /v1/waivers

Crea una excepcion de politica (waiver) para un `rule_id` especifico. Requiere rol `policy_editor` o `admin`.

```bash
curl -s -X POST http://safecontext-host:8000/v1/waivers \
  -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "API_KEY",
    "entity_pattern": "AKIA.*",
    "justification": "AWS test keys used in CI environment",
    "expires_at": "2026-12-31T23:59:59Z"
  }'
```

> **Validacion**: `entity_pattern` debe ser un regex valido. Un regex invalido retorna `422 Unprocessable Entity`.

### GET /v1/audit/{trace_id}

Recupera la evidencia de auditoria por `trace_id`. Requiere ser el owner de la operacion, o tener rol `reviewer` o `admin`. Otros usuarios reciben `403 Forbidden`.

### Documentacion OpenAPI interactiva

```
http://safecontext-host:8000/docs      # Swagger UI
http://safecontext-host:8000/redoc     # ReDoc
http://safecontext-host:8000/openapi.json  # Schema JSON
```

---

## 9. Manejo de errores

### Tabla de errores HTTP

| Código HTTP | Causa | Solución |
|---|---|---|
| `400 Bad Request` | Input inválido: campo faltante, formato incorrecto, `tool` desconocido | Verificar el schema del tool. Ver `/docs` |
| `401 Unauthorized` | Token ausente, expirado o inválido | Renovar el token. Verificar `Authorization: Bearer <token>` |
| `403 Forbidden` | Token válido pero sin permisos para el tool/operación | Verificar scopes del token. Contactar al administrador |
| `404 Not Found` | `trace_id` o `operation_id` no existe | Verificar que el `trace_id` sea correcto y de este tenant |
| `409 Conflict` | Operación ya completada o en estado incompatible con la acción solicitada | Verificar el estado actual con `GET /v1/scan/{trace_id}` |
| `422 Unprocessable Entity` | Schema válido pero valores inválidos (e.g. `confidence` fuera de rango) | Corregir los valores según la documentación del schema |
| `429 Too Many Requests` | Rate limit de 100 RPM superado para el `client_id` | Esperar el tiempo indicado en `Retry-After` |
| `500 Internal Server Error` | Error inesperado del servidor | Reportar con el `trace_id` del error al equipo SafeContext |
| `503 Service Unavailable` | Uno o más componentes degradados (PG, Redis, MinIO, OPA) | Consultar `GET /health` para identificar el componente afectado |

### Estructura canónica de error

Todos los errores tienen la misma estructura JSON:

```json
{
  "error": "validation_error",
  "message": "Field 'policy_name' is required",
  "trace_id": "550e8400-e29b-41d4-a716-446655440001",
  "details": {
    "field": "input.policy_name",
    "received": null,
    "expected": "string"
  }
}
```

El campo `trace_id` está presente cuando el error ocurrió dentro de una operación rastreable. Si ocurrió antes (e.g. validación de autenticación), `trace_id` es `null`.

### Manejo de errores en Python

```python
import httpx

try:
    result = sc.scan_and_sanitize(document)

except httpx.HTTPStatusError as e:
    error_body = e.response.json()

    if e.response.status_code == 401:
        print("Token inválido o expirado. Renovar credenciales.")

    elif e.response.status_code == 429:
        retry_after = e.response.headers.get("Retry-After", "60")
        print(f"Rate limit. Reintentar en {retry_after}s.")
        time.sleep(int(retry_after))

    elif e.response.status_code == 503:
        print(f"SafeContext degradado: {error_body}")
        # Implementar circuit breaker o fallback

    else:
        print(f"Error {e.response.status_code}: {error_body['message']}")
        print(f"trace_id para soporte: {error_body.get('trace_id')}")

except HumanReviewRequired as e:
    print(f"Requiere revisión humana. trace_id={e.trace_id}")
    # Encolar para revisión; no bloquear el proceso principal

except SafeContextError as e:
    print(f"Error SafeContext: {e}")
```

### Reintentos con backoff exponencial

```python
import random

def call_with_retry(fn, max_retries: int = 3, base_delay: float = 1.0):
    for attempt in range(max_retries):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (429, 503) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("Max retries exceeded")

result = call_with_retry(lambda: sc.scan(document))
```

---

## 10. Ejemplos completos

### 10.1 Scan y sanitize en Python (10 líneas)

```python
import httpx, os

sc_url, token = os.environ["SAFECONTEXT_URL"], os.environ["SAFECONTEXT_TOKEN"]
headers = {"Authorization": f"Bearer {token}", "X-Client-ID": "quick-script"}

def call(tool, data):
    r = httpx.post(f"{sc_url}/v1/mcp/call", headers=headers, json={"tool": tool, "input": data})
    r.raise_for_status()
    return r.json()["content"]

scan = call("safecontext.scan", {"document": open("informe.txt").read(), "policy_name": "base"})
if scan["findings"]:
    san = call("safecontext.sanitize", {"trace_id": scan["trace_id"], "redaction_type": "mask"})
    open("informe_sanitizado.txt", "w").write(san["sanitized_document"])
    print(f"Sanitizado: {len(san['redaction_map'])} redacciones. trace_id={scan['trace_id']}")
else:
    print("Documento limpio — sin hallazgos.")
```

### 10.2 Gate de CI/CD en bash (verificar antes del deploy)

```bash
#!/usr/bin/env bash
# safecontext-gate.sh
# Uso: ./safecontext-gate.sh <archivo_o_directorio>
# Exit 0: limpio. Exit 1: hallazgos críticos. Exit 2: error de conexión.

set -euo pipefail

SAFECONTEXT_URL="${SAFECONTEXT_URL:-http://safecontext-host:8000}"
SAFECONTEXT_TOKEN="${SAFECONTEXT_TOKEN:?ERROR: SAFECONTEXT_TOKEN requerido}"
CLIENT_ID="${SAFECONTEXT_CLIENT_ID:-ci-pipeline}"
POLICY="${SAFECONTEXT_POLICY:-base}"
FAIL_SEVERITY="${FAIL_SEVERITY:-high}"
TARGET="${1:-.}"

# Leer documento (simplificado; en producción usar la GitHub Action para directorios)
if [ -f "$TARGET" ]; then
    DOCUMENT=$(cat "$TARGET")
else
    # Para directorios: concatenar archivos de texto relevantes
    DOCUMENT=$(find "$TARGET" -type f \( -name "*.py" -o -name "*.ts" -o -name "*.env*" \) \
               -not -path "*/node_modules/*" -not -path "*/.git/*" \
               | head -50 | xargs cat 2>/dev/null || true)
fi

echo "[SafeContext] Escaneando '$TARGET' con política '$POLICY'..."

# Realizar scan
RESPONSE=$(curl -sf -X POST "${SAFECONTEXT_URL}/v1/mcp/call" \
    -H "Authorization: Bearer ${SAFECONTEXT_TOKEN}" \
    -H "X-Client-ID: ${CLIENT_ID}" \
    -H "Content-Type: application/json" \
    -d "{\"tool\": \"safecontext.scan\", \"input\": {\"document\": $(echo "$DOCUMENT" | jq -Rs .), \"policy_name\": \"${POLICY}\"}}" \
    2>/dev/null) || {
    echo "[SafeContext] ERROR: no se pudo conectar a SafeContext en ${SAFECONTEXT_URL}"
    exit 2
}

TRACE_ID=$(echo "$RESPONSE" | jq -r '.content.trace_id')
FINDINGS=$(echo "$RESPONSE" | jq '.content.findings | length')
CRITICAL=$(echo "$RESPONSE" | jq '[.content.findings[] | select(.severity == "critical")] | length')
HIGH=$(echo "$RESPONSE" | jq '[.content.findings[] | select(.severity == "high")] | length')

echo "[SafeContext] trace_id: ${TRACE_ID}"
echo "[SafeContext] Hallazgos: ${FINDINGS} total, ${CRITICAL} críticos, ${HIGH} high"

# Determinar resultado según severidad configurada
BLOCK=0
case "$FAIL_SEVERITY" in
    "critical") [ "$CRITICAL" -gt 0 ] && BLOCK=1 ;;
    "high")     [ "$CRITICAL" -gt 0 ] || [ "$HIGH" -gt 0 ] && BLOCK=1 ;;
    "medium")   [ "$(echo "$RESPONSE" | jq '[.content.findings[] | select(.severity != "low")] | length')" -gt 0 ] && BLOCK=1 ;;
esac

if [ "$BLOCK" -eq 1 ]; then
    echo "[SafeContext] BLOQUEADO — hallazgos en o por encima de severity=${FAIL_SEVERITY}"
    echo "[SafeContext] Evidencia: ${SAFECONTEXT_URL}/v1/audit/${TRACE_ID}"
    exit 1
else
    echo "[SafeContext] PASS — documento limpio"
    echo "SAFECONTEXT_TRACE_ID=${TRACE_ID}" >> "${GITHUB_OUTPUT:-/dev/null}" 2>/dev/null || true
    exit 0
fi
```

Uso en un pipeline:

```bash
# Instalar y ejecutar antes del deploy
chmod +x safecontext-gate.sh
./safecontext-gate.sh ./src && deploy_to_production
```

### 10.3 Integración con LangChain / LlamaIndex

#### LangChain — Tool personalizado

```python
from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
import httpx, os

class SafeContextScanTool(BaseTool):
    """LangChain tool que valida y sanitiza documentos via SafeContext."""

    name: str = "safecontext_scan_sanitize"
    description: str = (
        "Escanea y sanitiza un documento antes de procesarlo. "
        "SIEMPRE usar esta herramienta antes de analizar documentos de usuarios. "
        "Input: el texto completo del documento. "
        "Output: el documento sanitizado sin datos sensibles."
    )

    _base_url: str = os.environ.get("SAFECONTEXT_URL", "http://safecontext-host:8000")
    _headers: dict = {
        "Authorization": f"Bearer {os.environ.get('SAFECONTEXT_TOKEN', '')}",
        "X-Client-ID": "langchain-agent",
    }

    def _run(self, document: str) -> str:
        with httpx.Client(timeout=30) as client:
            # 1. Scan
            scan_r = client.post(f"{self._base_url}/v1/mcp/call", headers=self._headers,
                json={"tool": "safecontext.scan", "input": {"document": document, "policy_name": "base"}})
            scan_r.raise_for_status()
            scan = scan_r.json()["content"]

            if not scan["findings"]:
                return document  # limpio

            if scan["requires_human_review"]:
                return f"[SafeContext: documento requiere revisión humana. trace_id={scan['trace_id']}]"

            # 2. Sanitize
            san_r = client.post(f"{self._base_url}/v1/mcp/call", headers=self._headers,
                json={"tool": "safecontext.sanitize", "input": {"trace_id": scan["trace_id"], "redaction_type": "mask"}})
            san_r.raise_for_status()
            return san_r.json()["content"]["sanitized_document"]

    async def _arun(self, document: str) -> str:
        raise NotImplementedError("Use async version with httpx.AsyncClient")


# Configurar agente con SafeContext como herramienta obligatoria
llm = ChatAnthropic(model="claude-sonnet-4-6")
tools = [SafeContextScanTool()]

prompt = ChatPromptTemplate.from_messages([
    ("system", "Eres un asistente que analiza documentos. SIEMPRE debes usar safecontext_scan_sanitize antes de procesar cualquier documento."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

result = executor.invoke({"input": "Analiza este documento: El empleado Carlos Ruiz (carlos@empresa.com) solicitó vacaciones."})
```

#### LlamaIndex — Node PostProcessor

```python
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
import httpx, os
from typing import List, Optional

class SafeContextSanitizer(BaseNodePostprocessor):
    """
    LlamaIndex post-processor que sanitiza nodos antes de enviarlosa un LLM.
    Añadir al pipeline de query: query_engine = index.as_query_engine(
        node_postprocessors=[SafeContextSanitizer()]
    )
    """

    base_url: str = os.environ.get("SAFECONTEXT_URL", "http://safecontext-host:8000")
    token: str = os.environ.get("SAFECONTEXT_TOKEN", "")

    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Client-ID": "llamaindex-pipeline",
        }
        sanitized_nodes = []
        with httpx.Client(timeout=30) as client:
            for node_with_score in nodes:
                text = node_with_score.node.get_content()

                scan_r = client.post(f"{self.base_url}/v1/mcp/call", headers=headers,
                    json={"tool": "safecontext.scan", "input": {"document": text, "policy_name": "base"}})
                scan_r.raise_for_status()
                scan = scan_r.json()["content"]

                if not scan["findings"]:
                    sanitized_nodes.append(node_with_score)
                    continue

                san_r = client.post(f"{self.base_url}/v1/mcp/call", headers=headers,
                    json={"tool": "safecontext.sanitize", "input": {"trace_id": scan["trace_id"], "redaction_type": "mask"}})
                san_r.raise_for_status()

                node_with_score.node.set_content(san_r.json()["content"]["sanitized_document"])
                node_with_score.node.metadata["safecontext_trace_id"] = scan["trace_id"]
                sanitized_nodes.append(node_with_score)

        return sanitized_nodes


# Uso en LlamaIndex
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

documents = SimpleDirectoryReader("./documentos").load_data()
index = VectorStoreIndex.from_documents(documents)

query_engine = index.as_query_engine(
    node_postprocessors=[SafeContextSanitizer()],
    similarity_top_k=3,
)

response = query_engine.query("¿Cuáles son las políticas de vacaciones?")
# Todos los nodos fueron sanitizados por SafeContext antes de enviarlos al LLM
print(response)
```

---

*Documento generado a partir de DOC-0 v0.1.0, DOC-3 v0.1.0, infra/github-action/README.md y policies/README.md*
*Próxima revisión requerida: inicio de Fase 2 (adición de safecontext.approve v1.1.0)*
