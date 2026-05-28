# Manual 08 · Roles, Permisos y Segregación de Funciones

**Versión**: 1.0.0 · **Estado**: Activo · **Fecha**: 2026-05-25
**Audiencia**: Administradores, desarrolladores, auditores, agentes IA
**Fuente de verdad**: Código en `core/auth_oidc.py`, `api/v1/*.py`, `mcp/scopes.py`, `policies/base/safecontext.rego`
**Documentos relacionados**: [DOC-PRODUCTO.md](../DOC-PRODUCTO.md) §5, [Manual 07](./07_ADMIN_CONFIGURACION.md), [Manual 09](./09_SEGURIDAD_Y_COMPLIANCE.md)

---

## Tabla de contenidos

1. [Modelo de roles](#1-modelo-de-roles)
2. [Matriz de permisos por interfaz UI](#2-matriz-de-permisos-por-interfaz-ui)
3. [Matriz de permisos por endpoint REST](#3-matriz-de-permisos-por-endpoint-rest)
4. [Permisos MCP (tools y scopes)](#4-permisos-mcp-tools-y-scopes)
5. [Segregación de funciones (SoD)](#5-segregación-de-funciones-sod)
6. [Asignación de roles en Keycloak](#6-asignación-de-roles-en-keycloak)
7. [Políticas OPA por tenant](#7-políticas-opa-por-tenant)
8. [Guía para desarrolladores](#8-guía-para-desarrolladores)

---

## 1. Modelo de roles

SafeContext define **4 roles** exclusivamente. No existen roles adicionales.

| Rol | Propósito | Principio |
|---|---|---|
| `viewer` | Consultar operaciones propias y audit trail | Solo lectura, mínimo privilegio |
| `reviewer` | Aprobar o rechazar hallazgos escalados | Decisión humana sobre datos sensibles |
| `policy_editor` | Gestionar waivers y configurar políticas de detección | Control de excepciones con justificación |
| `admin` | Administración completa: tenants, SIEM, retención, purga GDPR | Acceso total, responsabilidad total |

### 1.1. Principios de diseño

- **Mínimo privilegio**: cada rol tiene exactamente los permisos que necesita, ninguno más.
- **Sin herencia implícita**: `admin` no "hereda" de `reviewer`. Cada endpoint declara explícitamente qué roles acepta.
- **Roles en JWT**: los roles se leen del claim `realm_access.roles` del token Keycloak. No se almacenan en base de datos de la aplicación.
- **Asignación única**: un usuario puede tener múltiples roles simultáneamente (ej: `reviewer` + `policy_editor`).

### 1.2. Decisión: eliminación de `platform_admin`

El rol `platform_admin` fue eliminado del codebase el 2026-05-24 (13 archivos modificados). No tenía respaldo en PRD, SAD ni Spec Ejecutable. Todos sus permisos fueron absorbidos 1:1 por `admin`. Ver [DOC-PRODUCTO.md](../DOC-PRODUCTO.md) §1 para contexto.

---

## 2. Matriz de permisos por interfaz UI

Cada página de la aplicación web valida el rol del usuario autenticado. El middleware de sesión (`middleware.ts`) redirige a `/login` si no hay sesión activa. Las rutas `/admin/*` tienen un guard adicional en `admin/layout.tsx`.

| Página | Ruta | `viewer` | `reviewer` | `policy_editor` | `admin` |
|---|---|:---:|:---:|:---:|:---:|
| Dashboard | `/dashboard` | ✅ Ver stats | ✅ Ver stats | ✅ Ver stats | ✅ Ver stats |
| Escaneo | `/scan` | ✅ Enviar documento | ✅ Enviar documento | ✅ Enviar documento | ✅ Enviar documento |
| Revisión | `/review` | ❌ | ✅ Aprobar/Rechazar | ❌ | ✅ Aprobar/Rechazar |
| Auditoría | `/audit` | ✅ Consultar trail | ✅ Consultar trail | ✅ Consultar trail | ✅ Consultar + descargar |
| Admin Layout | `/admin/*` | ❌ | ❌ | ❌ | ✅ |
| Admin Tenants | `/admin/tenants` | ❌ | ❌ | ❌ | ✅ CRUD tenants |
| Admin Tenant Detalle | `/admin/tenants/[id]` | ❌ | ❌ | ❌ | ✅ Config + SIEM test |
| Admin Waivers | `/admin/waivers` | ❌ | ❌ | ✅ Crear/Revocar | ✅ Crear/Revocar |
| Admin Retención | `/admin/retention` | ❌ | ❌ | ❌ | ✅ Config + purga |

**Nota sobre NavBar**: El enlace "Admin" en la barra de navegación solo se muestra si el usuario tiene rol `admin`. Se evalúa en `NavBar.tsx` con `hasRole('admin')`.

**Nota sobre Waivers**: La página `/admin/waivers` acepta tanto `policy_editor` como `admin` porque los waivers son excepciones de política, no configuración de infraestructura.

---

## 3. Matriz de permisos por endpoint REST

### 3.1. Endpoints de operación (cualquier usuario autenticado)

Estos endpoints requieren un token JWT válido (`require_auth`) pero no exigen un rol específico.

| Endpoint | Método | Autenticación | Roles | Descripción |
|---|---|---|---|---|
| `/v1/scan` | POST | Bearer JWT o MCP token | Cualquiera autenticado | Enviar documento para escaneo |
| `/v1/audit/{trace_id}` | GET | Bearer JWT | Cualquiera autenticado | Obtener evidencia de auditoría |
| `/v1/audit/{trace_id}/sarif` | GET | Bearer JWT | Cualquiera autenticado | Exportar en formato SARIF |
| `/v1/waivers` | GET | Bearer JWT | Cualquiera autenticado | Listar waivers activos |

**Referencia en código**: `core/auth_oidc.py:require_auth` — valida JWT + MFA.

### 3.2. Endpoints de revisión (reviewer o admin)

| Endpoint | Método | Guard | Roles | Descripción |
|---|---|---|---|---|
| `/v1/review/pending` | GET | `require_reviewer` | `reviewer`, `admin` | Listar hallazgos escalados |
| `/v1/review/{finding_id}/approve` | POST | `require_reviewer` + SoD | `reviewer`, `admin` | Aprobar hallazgo + crear redacción |
| `/v1/review/{finding_id}/reject` | POST | `require_reviewer` | `reviewer`, `admin` | Rechazar hallazgo |

**Referencia en código**: `core/auth_oidc.py:require_reviewer` — acepta `reviewer` o `admin`.

### 3.3. Endpoints de waivers (policy_editor o admin)

| Endpoint | Método | Guard | Roles | Descripción |
|---|---|---|---|---|
| `/v1/waivers` | POST | `_require_privileged` | `policy_editor`, `admin` | Crear waiver (justificación requerida) |
| `/v1/waivers/{waiver_id}` | DELETE | `_require_privileged` | `policy_editor`, `admin` | Revocar waiver |

**Referencia en código**: `api/v1/waivers.py:_require_privileged` — acepta `policy_editor` o `admin`.

### 3.4. Endpoints de administración (solo admin)

| Endpoint | Método | Guard | Roles | Descripción |
|---|---|---|---|---|
| `/v1/admin/tenants` | GET | `_require_admin` | `admin` | Listar todos los tenants |
| `/v1/admin/tenants` | POST | `_require_admin` | `admin` | Crear tenant |
| `/v1/admin/tenants/{id}` | GET | `_require_admin` | `admin` | Detalle de tenant |
| `/v1/admin/tenants/{id}` | PATCH | `_require_admin` | `admin` | Actualizar configuración |
| `/v1/admin/tenants/{id}` | DELETE | `_require_admin` | `admin` | Desactivar tenant (soft-delete) |
| `/v1/admin/tenants/{id}/siem/test` | POST | `_require_admin` | `admin` | Probar conectividad SIEM |
| `/v1/admin/tenants/{id}/purge` | POST | `_require_admin` | `admin` | Ejecutar purga GDPR manual |
| `/v1/admin/tenants/{id}/certificates` | GET | `_require_reader` | `admin`, `reviewer` | Listar certificados de borrado |
| `/v1/admin/tenants/{id}/certificates/{cert}` | GET | `_require_reader` | `admin`, `reviewer` | Obtener certificado específico |

**Nota**: Los certificados de borrado son consultables por `reviewer` porque pueden necesitar verificar el cumplimiento GDPR durante auditorías. La purga en sí solo la ejecuta `admin`.

**Referencia en código**: `api/v1/admin_tenants.py:_require_admin`, `api/v1/admin_retention.py:_require_reader`.

---

## 4. Permisos MCP (tools y scopes)

El servidor MCP expone herramientas para agentes IA. La autenticación usa OAuth 2.1 + PKCE (`mcp/auth.py`). Cada herramienta requiere un scope específico.

### 4.1. Tabla de tools y scopes

| Tool MCP | Scope requerido | Funcionalidad |
|---|---|---|
| `safecontext.scan` | `mcp:scan` | Escanear documento para detectar datos sensibles |
| `safecontext.sanitize` | `mcp:sanitize` | Sanitizar (redactar) contenido detectado |
| `safecontext.classify` | `mcp:classify` | Clasificar nivel de sensibilidad de secciones |
| `safecontext.audit` | `mcp:audit` | Consultar audit trail por trace_id |
| `safecontext.policy.get` | `mcp:policy` | Obtener política de detección activa |
| `safecontext.approve` | `mcp:approve` | Aprobar/rechazar hallazgos (solo con consentimiento) |

**Referencia en código**: `mcp/scopes.py:TOOL_SCOPES` — diccionario tool→scope.

### 4.2. Validación de scopes

```python
# mcp/scopes.py — extracto funcional
def require_tool_scope(tool_name: str, token_payload: dict) -> None:
    required = TOOL_SCOPES.get(tool_name)
    if required is None:
        return  # tool desconocido → el router maneja 404
    granted = set(token_payload.get("scope", "").split())
    if required not in granted:
        raise HTTPException(403, f"Insufficient scope. Required: {required}")
```

Los scopes se otorgan durante el flujo OAuth 2.1 con consentimiento explícito del usuario. El servidor MCP **nunca** otorga scopes sin consentimiento (ver `mcp/scopes.py:require_tool_scope`).

### 4.3. Rate limiting MCP

Las llamadas MCP están sujetas a rate limiting configurable:
- **Por defecto**: `MCP_RATE_LIMIT_RPM` requests por minuto por `client_id`
- **Implementación**: Redis sorted sets (multi-instancia) con fallback in-memory (single worker)
- **Referencia**: `core/auth_oidc.py:check_rate_limit_redis`, `check_rate_limit`

---

## 5. Segregación de funciones (SoD)

### 5.1. Regla fundamental

> **Quien escanea un documento no puede aprobar los hallazgos de ese mismo escaneo.**

Esta regla previene que un actor malicioso envíe un documento con datos sensibles y luego apruebe su propia redacción, eludiendo la revisión humana independiente.

### 5.2. Implementación técnica

```python
# core/auth_oidc.py — extracto
def check_self_approval(actor_id: str, approver_payload: dict) -> None:
    approver_sub = approver_payload.get("sub", "")
    if actor_id == approver_sub:
        raise HTTPException(
            status_code=403,
            detail="Self-approval not permitted (segregation of duties)",
        )
```

### 5.3. Dónde se aplica

| Endpoint | Verificación SoD | Detalle |
|---|---|---|
| `POST /v1/review/{id}/approve` | ✅ `check_self_approval` | Compara `operation.actor_id` con `approver.sub` |
| `POST /v1/review/{id}/reject` | ❌ No aplica | Rechazar es una acción conservadora, no requiere SoD |
| Creación de waivers | ❌ No aplica | Los waivers son excepciones de política, no decisiones sobre datos específicos |

### 5.4. Flujo visual de SoD

```
Usuario A (viewer/admin)          Usuario B (reviewer/admin)
        │                                    │
        ├─── POST /v1/scan ──────►           │
        │    actor_id = UUID(A)              │
        │                                    │
        │    [Workers procesan, escalan]      │
        │                                    │
        │    GET /v1/review/pending ◄────────┤
        │                                    │
        ├─── POST /review/{id}/approve ──►   │  ← 403: Self-approval not permitted
        │                                    │
        │    POST /review/{id}/approve ◄─────┤  ← ✅ OK: actor_id ≠ approver_sub
        │                                    │
```

---

## 6. Asignación de roles en Keycloak

### 6.1. Realm y cliente

- **Realm**: `safecontext`
- **Cliente UI**: `safecontext-ui` (OIDC, public client, PKCE)
- **Cliente API**: `safecontext-api` (audience mapper incluido en access token)
- **Claims de roles**: `realm_access.roles` en el JWT

### 6.2. Cómo asignar un rol

1. Acceder a Keycloak Admin Console (`http://localhost:8080/admin`)
2. Seleccionar realm `safecontext`
3. Ir a **Users** → seleccionar usuario
4. Tab **Role mapping** → **Assign role**
5. Seleccionar uno o más roles: `viewer`, `reviewer`, `policy_editor`, `admin`
6. Guardar

### 6.3. Usuarios de desarrollo

El realm de desarrollo incluye usuarios pre-configurados:

| Usuario | Contraseña | Roles | Propósito |
|---|---|---|---|
| `dev-viewer` | `dev-viewer` | `viewer` | Probar flujo de solo lectura |
| `dev-reviewer` | `dev-reviewer` | `reviewer` | Probar flujo de revisión + SoD |
| `dev-editor` | `dev-editor` | `policy_editor` | Probar gestión de waivers |
| `dev-admin` | `dev-admin` | `admin` | Probar todas las funcionalidades |

### 6.4. Resolución de tenant

El tenant se resuelve desde el JWT:
- Claim personalizado `tenant_id` si está presente
- Fallback a `DEFAULT_TENANT_ID` (`00000000-0000-0000-0000-000000000000`)

**Referencia en código**: `api/v1/scan.py:_resolve_scan_actor`, `api/v1/waivers.py` línea 87.

---

## 7. Políticas OPA por tenant

### 7.1. Evaluación de políticas

OPA (Open Policy Agent) evalúa las políticas de detección. Existen dos modos:

| Modo | Función Rego | Cuándo se usa |
|---|---|---|
| Base | `decision(findings)` | Sin configuración de tenant |
| Multi-tenant | `tenant_decision(findings, waivers, tenant_config)` | Con `tenant_config` presente |

### 7.2. Configuración por tenant

Cada tenant puede personalizar:

| Parámetro | Tipo | Efecto |
|---|---|---|
| `confidence_overrides` | `{entity_type: float}` | Ajustar umbral de confianza por tipo de entidad |
| `severity_overrides` | `{entity_type: string}` | Cambiar severidad base (low/medium/high/critical) |
| `blocked_entity_types` | `[string]` | Bloquear siempre ciertos tipos de entidad |

**Ejemplo**: un tenant financiero puede configurar `{"blocked_entity_types": ["SSN", "CREDIT_CARD"]}` para bloquear siempre estos tipos, independientemente de la confianza del detector.

### 7.3. Waivers en OPA

Los waivers (excepciones de política) se evalúan en Rego:

1. `should_waive(finding, waivers)` — verifica si algún waiver activo coincide con el `rule_id` del hallazgo y el patrón regex del waiver coincide con el texto detectado.
2. `active_findings_after_waivers(findings, waivers)` — filtra hallazgos cubiertos por waivers activos.

Los waivers requieren:
- `rule_id` (qué regla se exceptúa)
- `entity_pattern` (regex válido del texto a exceptuar)
- `justification` (texto libre, mínimo 20 caracteres en la UI)
- `expires_at` (opcional, fecha de expiración)

**Referencia en código**: `policies/base/safecontext.rego:should_waive`, `decision_with_waivers`.

---

## 8. Guía para desarrolladores

### 8.1. Agregar un nuevo endpoint protegido

**Solo admin:**
```python
from core.auth_oidc import get_roles, require_auth

_ADMIN_ROLE = "admin"

def _require_admin(payload: dict) -> None:
    if _ADMIN_ROLE not in get_roles(payload):
        raise HTTPException(status_code=403, detail="admin role required")

@router.get("/mi-endpoint")
async def mi_endpoint(
    auth_payload: Annotated[dict, Depends(require_auth)],
):
    _require_admin(auth_payload)
    # ... lógica
```

**Reviewer o admin:**
```python
from core.auth_oidc import require_reviewer

@router.get("/mi-endpoint")
async def mi_endpoint(
    actor: dict = Depends(require_reviewer),
):
    # ... lógica (actor ya validado como reviewer o admin)
```

**Múltiples roles personalizados:**
```python
_ALLOWED_ROLES = ("policy_editor", "admin")

def _require_privileged(payload: dict) -> None:
    roles = get_roles(payload)
    if not any(r in roles for r in _ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Requires policy_editor or admin role")
```

### 8.2. Agregar verificación SoD

Si tu endpoint implica que un usuario aprueba una acción de otro:

```python
from core.auth_oidc import check_self_approval

# En el handler del endpoint:
check_self_approval(str(operation.actor_id), approver_payload)
```

### 8.3. Proteger una página en el frontend

**Guard de rol en layout (patrón admin):**
```tsx
// app/admin/layout.tsx — extracto funcional
const session = useSession();
if (!session || !session.roles.includes('admin')) {
  redirect('/dashboard');
}
```

**Mostrar/ocultar elementos por rol:**
```tsx
// NavBar.tsx — patrón de link condicional
{hasRole('admin') && <Link href="/admin">Admin</Link>}
```

**Verificar permiso antes de acción:**
```tsx
// review/page.tsx — botón aprobar solo para reviewer/admin
const canReview = hasRole('reviewer') || hasRole('admin');
{canReview && <Button onClick={handleApprove}>Aprobar</Button>}
```

### 8.4. Agregar un nuevo rol

> ⚠️ **No se recomienda agregar roles sin actualizar DOC-PRODUCTO.md, este manual y las políticas OPA.**

Si es necesario:

1. Definir el rol en Keycloak (realm `safecontext`)
2. Crear usuario de prueba con el nuevo rol
3. Agregar guards en los endpoints relevantes (backend)
4. Agregar verificaciones en las páginas relevantes (frontend)
5. Actualizar la política OPA si el rol afecta evaluación de políticas
6. Actualizar este manual (secciones §2, §3, §4)
7. Actualizar `DOC-PRODUCTO.md` §5
8. Agregar tests que verifiquen el nuevo rol

### 8.5. Agregar un nuevo scope MCP

1. Agregar la entrada en `mcp/scopes.py:TOOL_SCOPES`
2. El scope se valida automáticamente por `require_tool_scope()`
3. Configurar el scope en el cliente OAuth de Keycloak
4. Actualizar este manual (sección §4)

---

## Resumen de guards por código fuente

| Guard | Archivo | Roles aceptados | Usado en |
|---|---|---|---|
| `require_auth` | `core/auth_oidc.py:168` | Cualquier JWT válido + MFA | `/v1/scan`, `/v1/audit/*`, `GET /v1/waivers` |
| `require_role(role)` | `core/auth_oidc.py:154` | Rol específico parametrizado | Factory genérico |
| `require_reviewer` | `core/auth_oidc.py:256` | `reviewer`, `admin` | `/v1/review/*` |
| `require_admin` | `core/auth_oidc.py:267` | `admin` | Dependency inyectable |
| `_require_admin` | `api/v1/admin_tenants.py:34` | `admin` | Todos los endpoints `/admin/tenants/*` |
| `_require_admin` | `api/v1/admin_siem.py:27` | `admin` | `/admin/tenants/{id}/siem/test` |
| `_require_admin` | `api/v1/admin_retention.py:33` | `admin` | `/admin/tenants/{id}/purge` |
| `_require_reader` | `api/v1/admin_retention.py:41` | `admin`, `reviewer` | `/admin/tenants/{id}/certificates*` |
| `_require_privileged` | `api/v1/waivers.py:31` | `policy_editor`, `admin` | `POST /v1/waivers`, `DELETE /v1/waivers/{id}` |
| `check_self_approval` | `core/auth_oidc.py:277` | N/A (SoD check) | `POST /v1/review/{id}/approve` |
| `require_tool_scope` | `mcp/scopes.py:17` | N/A (scope check) | Todas las tools MCP |

---

*Última actualización: 2026-05-25 · Versión 1.0.0*
