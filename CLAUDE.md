# CLAUDE.md — SafeContext
**Autoridad**: Instrucciones operacionales para agentes Claude Code  
**Versión**: 1.0.0 · **Actualizado**: 2026-05-23 · **Próxima revisión**: 2026-06-06  
**Responsable**: Usuario (sincronizar con ROADMAP.md §11 cada 2 semanas)

---

## Table of Contents
1. [Entrada rápida](#entrada-rápida) — Para agentes nuevos (5 min)
2. [Principios invariantes](#principios-invariantes) — Reglas duras que nunca romper
3. [Mapa de autoridad](#mapa-de-autoridad) — Qué documento consultar para qué
4. [Flujo de trabajo](#flujo-de-trabajo) — Cómo abordar una tarea
5. [Patrones técnicos](#patrones-técnicos) — Código real del proyecto
6. [Límites de autonomía](#límites-de-autonomía) — Qué puedo/no puedo hacer
7. [Checklist de calidad](#checklist-de-calidad) — Antes de marcar como hecho
8. [Troubleshooting](#troubleshooting) — Errores comunes
9. [Changelog](#changelog) — Historial de cambios

---

## Entrada rápida

**Eres un agente autónomo. Tu trabajo: ejecutar, no preguntar.**

### En 2 minutos

1. **¿Qué tengo que hacer?** → Leer `apps/docs/ROADMAP.md §7` (tarea específica)
2. **¿Cómo lo hago?** → Leer patrón en §5 abajo + leer código existente (grep)
3. **¿Existe ya?** → Grep antes de escribir. Si existe: leer, no reimplementar
4. **¿Necesito confirmar?** → Ver §6. Si duda: leer ROADMAP + AGENTS.md
5. **¿Cómo sé que acabé?** → Checklist §7. Si pasa todo: hecho

**Si algo no encaja: lee ROADMAP.md §11 (Resumen), luego AGENTS.md (tu rol).**

### En 30 segundos (si ya conoces el proyecto)

```bash
# Estado actual
Estado: Madurez 4.5/5 | Código: 0 gaps | Frontend: 43/43 tests ✅
Fuente: apps/docs/ROADMAP.md (2026-05-21)

# Quick checks
grep -r "función/clase/endpoint" apps/  # ¿Existe?
pytest tests/ -k "test_" -v              # ¿Tests pasan?
npm test                                 # Frontend tests
```

---

## Principios invariantes

**Estos NO son opcionales. Son límites del proyecto.**

### 🔴 NUNCA

```
• Reimplementar código existente sin leerlo primero
  └─ Grep siempre. Lee el código antes de escribir el tuyo.

• Ignorar criterios de aceptación en ROADMAP §7
  └─ Si una tarea dice "test coverage ≥80%", es 80% o no está hecho.

• Crear abstracciones o refactorizar sin autorización
  └─ Si no está en ROADMAP §7: no es trabajo autorizado.

• Cambiar decisiones arquitectónicas (ADRs)
  └─ No cambies PostgreSQL por MongoDB sin pasar por ADR process.

• Enviar datos sensibles a servicios externos
  └─ SafeContext opera offline. Nunca hagas HTTP a servicios SaaS no autorizados.

• Tocar policies OPA sin entender ADR-005
  └─ Política = seguridad. Cambiar política = cambiar cómo se decide lo que es seguro.

• Marcar una tarea como "hecho" sin evidencia
  └─ Test pasando, log correcto, métrica alcanzada. Punto.
```

### 🟢 SIEMPRE

```
• Leer ROADMAP.md antes de cualquier tarea
  └─ 10 min leyendo = 2 horas no haciendo trabajo inútil.

• Incluir trace_id + actor_id + policy_version en operaciones críticas
  └─ Audit trail es invariante. Sin esto, no es completo.

• Tests para código nuevo (mínimo 80% cobertura)
  └─ Backend: pytest. Frontend: Jest. Workers: pytest.

• Commits con mensaje claro + firma
  └─ `feat(backend): add GET /v1/operations` + Co-Authored-By

• Verificar que PostgreSQL es la fuente de verdad
  └─ Redis es efímero. DB es registro inmutable. ADR-001.

• Leer el test existente antes de escribir uno nuevo
  └─ Aprenderás el patrón del proyecto, no el tuyo.
```

---

## Mapa de autoridad

**Si necesitas saber X, lee Y. Punto. No hagas inferencias.**

| Necesitas saber | Documento | Sección | Tiempo |
|---|---|---|---|
| Estado actual del proyecto | `ROADMAP.md` | §11 | 2 min |
| Qué está hecho vs pendiente | `ROADMAP.md` | §5–§7 | 15 min |
| Criterios de aceptación de tarea | `ROADMAP.md` | §7 (tabla) | 2 min |
| Por qué existe SafeContext | `ROADMAP.md` | §1–§3 | 10 min |
| Arquitectura general | `DOC-0_UNIFIED.md` | §3 | 15 min |
| Decisión específica (ej: por qué PostgreSQL) | `adr/ADR-001..011` | Lee el ADR | 5 min |
| Requisitos funcionales | `DOC-1_PRD.md` | Requisitos | 20 min |
| Modelo de datos | `DOC-2_SAD.md` | §2 | 10 min |
| Spec técnica | `DOC-3_SPEC.md` | Criterios por fase | 30 min |
| Guía técnica (backend/frontend/infra) | `SKILLS.md` | Sección de dominio | 10 min |
| Cómo funciona operativamente | `manuals/03_USUARIO.md` | Flujos | 15 min |
| Cómo integrar MCP | `manuals/04_INTEGRACION_MCP_API.md` | Integración | 10 min |
| Procedimiento DR/DLQ/rotación | `runbooks/` | Runbook específico | 5 min |
| Cómo navegar el repo | `WORKSPACE.md` | Estructura | 5 min |
| Tu rol como agente | `AGENTS.md` | Rol + principios | 10 min |

**Regla de oro**: Si algo contradice ROADMAP.md §11, el ROADMAP gana.

---

## Flujo de trabajo

**Procesa toda tarea así. En orden. No saltes pasos.**

```
PASO 1: Leer tarea en ROADMAP §7
        ↓
        Verificar: ¿Está marcada como autorizada?
        ✗ No → STOP. No es trabajo autorizado.
        ✓ Sí → continúa

PASO 2: Leer criterios de aceptación (AC)
        ↓
        Entender: ¿Qué es "hecho"?
        (ej: "test con 36 casos cubre API keys, JWT, connection strings")
        
PASO 3: Grep en repo
        ↓
        ¿Existe código similar o idéntico?
        ✓ Sí → lee ese código. Aprende el patrón del proyecto.
        ✗ No → continúa

PASO 4: Leer guía técnica (SKILLS.md)
        ↓
        Entender: Patrones, convenciones, librerías permitidas
        
PASO 5: Implementar
        ↓
        Escribe código, tests, documentación
        
PASO 6: Ejecutar tests locales
        ↓
        ¿Todos los tests pasan?
        ✗ No → identifica causa, corrige, va a PASO 5
        ✓ Sí → continúa

PASO 7: Checklist de calidad (§7 abajo)
        ↓
        ¿Todos los puntos marcan ✅?
        ✗ No → identifica cuál no, corrige, va a PASO 5
        ✓ Sí → continúa

PASO 8: Commit + evidencia
        ↓
        git commit con mensaje claro
        Documenta: qué cambió, por qué, evidencia (test output, métrica)
```

---

## Patrones técnicos

**Código real del proyecto. Cópialos. No improvises.**

### Backend (FastAPI + Python 3.14)

```python
# ✅ Patrón: Endpoint con auth + logging + audit trail

from typing import Annotated
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from core.auth_oidc import require_auth      # Bearer token → claims
from core.logging import get_logger           # structlog
from db.session import get_db                 # AsyncSession
from db.models.operation import Operation     # SQLAlchemy model

router = APIRouter(tags=["scan"])
log = get_logger(__name__)

class ScanRequest(BaseModel):
    document: str
    policy_name: str = "default"

class ScanResponse(BaseModel):
    trace_id: UUID
    status: str
    findings_count: int

@router.post("/scan", response_model=ScanResponse, status_code=202)
async def scan_document(
    request: ScanRequest,
    _actor: Annotated[dict, Depends(require_auth)],  # JWT claims
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScanResponse:
    """
    Scan a document for sensitive data.
    
    Returns trace_id for audit trail lookup.
    Any authenticated user can scan.
    """
    trace_id = uuid4()
    actor_id = _actor["sub"]  # JWT subject claim
    
    log.info(
        "scan.initiated",
        trace_id=str(trace_id),
        actor_id=actor_id,
        policy=request.policy_name,
    )
    
    # Create operation record (audit trail)
    operation = Operation(
        trace_id=trace_id,
        actor_id=actor_id,
        artifact_digest="<to be computed>",
        policy_version="<from registry>",
        status="pending",
    )
    db.add(operation)
    await db.commit()
    
    # Queue detector agent
    # (workers are autonomous, trace_id flows through)
    
    return ScanResponse(
        trace_id=trace_id,
        status="pending",
        findings_count=0,
    )
```

**Puntos clave:**
- `require_auth` inyecta claims del JWT (sub, realm_access.roles, etc.)
- `trace_id` presente en TODA operación
- `actor_id` extraído de `_actor["sub"]`
- `log.info()` con contexto estructurado
- Response incluye `trace_id` para audit trail lookup
- Docstring explícito (qué hace, quién puede)

### Frontend (Next.js 16.2 + TypeScript)

```typescript
// ✅ Patrón: Página con session + API call + error handling

'use client'

import { useState, useCallback, useEffect } from 'react'
import Link from 'next/link'
import { useSession } from '@/hooks/useSession'
import { apiClient } from '@/lib/api-client'
import { Toast, LoadingSpinner, EmptyState, SeverityBadge } from '@/components'

interface ScanResult {
  trace_id: string
  status: 'pending' | 'completed' | 'escalated' | 'rejected'
  findings_count: number
  findings: Array<{
    id: string
    rule_id: string
    severity: 'low' | 'medium' | 'high' | 'critical'
    message: string
    span: { start: number; end: number }
  }>
}

export default function ScanPage() {
  const { session, role } = useSession()  // Cookie httpOnly → claims
  const [document, setDocument] = useState('')
  const [result, setResult] = useState<ScanResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState<{ type: 'error' | 'success'; msg: string } | null>(null)

  const handleScan = useCallback(async () => {
    if (!document.trim()) {
      setToast({ type: 'error', msg: 'Document cannot be empty' })
      return
    }

    setLoading(true)
    try {
      const res = await apiClient('/v1/scan', {
        method: 'POST',
        body: { document, policy_name: 'default' },
      })
      // apiClient injects Bearer token automatically
      // 401 → clears session, redirects to /login
      // 403 → throws ForbiddenError (backend did SoD check)
      // 422 → validation error
      
      setResult(res)
      setToast({ type: 'success', msg: 'Scan completed' })
      
      // Poll for completion if status === 'pending'
      if (res.status === 'pending') {
        pollForResult(res.trace_id)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err)
      setToast({ type: 'error', msg: message })
    } finally {
      setLoading(false)
    }
  }, [document])

  const pollForResult = async (traceId: string) => {
    let attempts = 0
    const maxAttempts = 60  // 5 min with 5s interval
    
    const poll = async () => {
      if (attempts >= maxAttempts) {
        setToast({ type: 'error', msg: 'Scan timeout' })
        return
      }
      
      attempts++
      await new Promise(r => setTimeout(r, 5000))  // 5s interval
      
      try {
        const res = await apiClient(`/v1/operations?trace_id=${traceId}`)
        if (res.items[0]?.status !== 'pending') {
          setResult(res.items[0])
          if (res.items[0]?.status === 'escalated') {
            setToast({ type: 'success', msg: 'Review required — see /review' })
          }
        } else {
          poll()  // Keep polling
        }
      } catch (err) {
        console.error('Poll error:', err)
        poll()
      }
    }
    
    poll()
  }

  if (!session) {
    return <div>Redirecting to login...</div>
  }

  return (
    <main className="p-6">
      <h1>Scan Document</h1>
      
      <textarea
        value={document}
        onChange={(e) => setDocument(e.target.value)}
        placeholder="Paste document content here..."
        className="w-full p-4 border rounded"
        rows={10}
      />
      
      <button
        onClick={handleScan}
        disabled={loading}
        className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
      >
        {loading ? <LoadingSpinner /> : 'Scan'}
      </button>
      
      {result && (
        <div className="mt-8">
          <h2>Results (trace_id: {result.trace_id})</h2>
          
          {result.findings_count === 0 ? (
            <EmptyState msg="No sensitive data detected" />
          ) : (
            <div className="space-y-4">
              {result.findings.map((f) => (
                <div key={f.id} className="border p-4 rounded">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={f.severity} />
                    <span className="font-mono text-sm">{f.rule_id}</span>
                  </div>
                  <p className="mt-2">{f.message}</p>
                  {result.status === 'escalated' && (
                    <Link href={`/review?trace_id=${result.trace_id}`}>
                      → Review and approve
                    </Link>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {toast && (
        <Toast
          type={toast.type}
          message={toast.msg}
          onClose={() => setToast(null)}
        />
      )}
    </main>
  )
}
```

**Puntos clave:**
- `useSession()` → acceso a claims del JWT
- `apiClient()` inyecta Bearer token automáticamente
- Maneja 401 (sesión expirada), 403 (SoD), 422 (validación)
- Polling para resultados async
- Componentes reutilizables (SeverityBadge, Toast, etc.)
- Docstrings en funciones críticas

### Patrones de seguridad (code review 2026-05-23)

```python
# ✅ Segregation of duties — impedir auto-aprobacion
from core.auth_oidc import check_self_approval
check_self_approval(str(operation.actor_id), actor)  # raises 403 if same user

# ✅ Audit access control — solo owner, reviewer o admin
roles = actor.get("realm_access", {}).get("roles", [])
is_privileged = "reviewer" in roles or "admin" in roles
is_owner = result.operation.get("actor_id") == actor_id
if not is_owner and not is_privileged:
    raise HTTPException(status_code=403, detail="Access denied")
```

```python
# ✅ Span-merging en sanitizacion (evita corrupcion con spans solapados)
sorted_findings = sorted(findings, key=lambda x: (x.span_start, x.span_end))
merged: list[tuple[int, int, list]] = []
for f in sorted_findings:
    if merged and f.span_start < merged[-1][1]:
        prev_start, prev_end, prev_fs = merged[-1]
        merged[-1] = (prev_start, max(prev_end, f.span_end), prev_fs + [f])
    else:
        merged.append((f.span_start, f.span_end, [f]))
for start, end, group in reversed(merged):  # right-to-left to preserve offsets
    sanitized = sanitized[:start] + replacement + sanitized[end:]
```

### Testing

```bash
# Backend
cd apps/api
pytest tests/api/test_scan.py::test_scan_creates_operation -v
pytest tests/api/ --cov=api/v1 --cov-report=term-missing

# Frontend
cd apps/ui
npm test -- --testPathPattern="scan.test.tsx" --coverage
npm test                  # All tests

# E2E (requiere docker compose --profile auth up)
cd apps/ui
npx playwright test              # Run all E2E tests
npx playwright test --list       # List tests without running

# Workers
cd apps/workers
pytest tests/ml/test_regex_detector.py -v
pytest tests/ --cov=workers --cov-report=html

# OPA policies (via Docker)
docker run --rm -v ./apps/policies:/policies openpolicyagent/opa:1.4.0 test /policies -v
```

---

## Límites de autonomía

**Estos son los límites. No sorpresas.**

### ✅ Autonomía total (sin confirmar)

```
□ Leer archivos
□ Escribir código en rutas existentes
  └─ apps/api/api/v1/*.py
  └─ apps/ui/src/app/*/page.tsx
  └─ apps/workers/agents/*.py
  
□ Escribir tests (pytest, Jest)
□ Escribir documentación
□ Ejecutar tests locales
□ Crear commits en rama actual
```

### ⚠️ Requiere confirmación previa

```
□ Nueva migración Alembic
  └─ Cambio de schema DB = contrato de datos que puede romper
  
□ Nuevo endpoint REST
  └─ Interface pública. Cambio puede afectar clientes.
  
□ Nuevo tool schema MCP
  └─ Interface pública del MCP Server.
  
□ Cambios a políticas OPA
  └─ Política = seguridad. Cambio puede debilitar el sistema.
  
□ Cambios a .github/workflows/*
  └─ CI/CD = control de calidad. Cambio puede permitir código roto.

□ Uso de nueva librería / dependencia
  └─ Lock-in, supply chain risk. Revisar antes.
```

**Cómo confirmar**: Mensaje explícito del usuario. "Sí, procede" o "Aprobado".

### ❌ Nunca (incluso con confirmación)

```
□ Cambiar decisiones arquitectónicas (ADRs)
  └─ Requiere RFC + discusión arquitectónica, fuera del scope de agente.

□ Refactorizar código existente
  └─ Si no está en ROADMAP §7 como tarea autorizada: es deuda técnica opaca.

□ Crear abstracciones no solicitadas
  └─ "The rule of three": deja que se repita 2 veces antes de abstraer.

□ Ignorar test failando
  └─ "Todo está bien excepto este test" = no está hecho.

□ Documentar "por hacer después"
  └─ No hay "TODO, implementar en F6". Está o no está.
```

---

## Checklist de calidad

**Antes de marcar tarea como "hecho": verifica esto.**

### Para cualquier tarea

```
□ ROADMAP.md §7 — ¿Cumplí todos los AC (Acceptance Criteria)?
  └─ Si dice "test coverage ≥80%": verificar % en output de test.
  └─ Si dice "SARIF output": verificar que endpoint retorna SARIF válido.
  └─ Si dice "funciona offline": verificar que no hay HTTP a externos.

□ Tests — ¿Todos pasan?
  pytest tests/api/test_scan.py -v
  npm test -- audit.test.tsx -v
  
  ✓ Verde completo
  ✗ Rojo en cualquier test = no está hecho

□ Coverage — ¿Mínimo 80% en código nuevo?
  pytest tests/ --cov=api/v1 --cov-report=term-missing
  
  ✓ 80%+ en nuevas líneas
  ✗ <80% = agregar tests

□ Documentación — ¿Docstring claro?
  def handler(...): 
    """Qué hace. Quién puede. Retorna qué."""
  
□ Logs/Audit — ¿Trace_id presente en operaciones críticas?
  log.info("evento", trace_id=..., actor_id=..., policy_version=...)
  
□ Commit — ¿Mensaje claro + firma?
  git commit -m "feat(backend): implement GET /v1/operations"
  git log --oneline -1
```

### Por tipo de cambio

#### Si escribiste endpoint REST

```
□ ¿Incluye @require_auth?
  (Usuario anónimo no puede llamar)

□ ¿Response incluye trace_id?
  (Auditabilidad: usuario puede reportar qué sucedió)

□ ¿Validación 422 en inputs inválidos?
  (ej: date string malformado)

□ ¿Docstring explícito?
  """Get operations filtered by status.
  Requires 'viewer' role. Returns paginated list with aggregates."""

□ ¿Test cubre happy path + errores?
  test_get_operations_returns_list()
  test_get_operations_invalid_date_returns_422()
  test_get_operations_requires_auth()
```

#### Si escribiste página frontend

```
□ ¿Usa useSession() para verificar rol?
  (No puedo llegar a /admin sin rol admin)

□ ¿Maneja 401/403 correctamente?
  (401 → limpia sesión, redirige /login)
  (403 → muestra error, no crash)

□ ¿Hay loading state?
  (usuario ve spinner mientras espera)

□ ¿Hay error toast?
  (usuario ve qué salió mal)

□ ¿Test con React Testing Library?
  render(<ScanPage />)
  await waitFor(() => screen.getByText(...))
  expect(screen.getByRole('button', { name: /Scan/ })).toBeEnabled()
```

#### Si escribiste worker / agent

```
□ ¿Es idempotente?
  (llamarla 2 veces = mismo resultado que 1 vez)

□ ¿Usa idempotency_key para detectar duplicados?
  (BD: idempotency_key UNIQUE index)

□ ¿Retorna en 3 intentos o → DLQ?
  (dramatiq.retry(max_retries=3, ...)

□ ¿Incluye trace_id en logs?
  (log.info("evento", trace_id=..., actor_id=...))

□ ¿Test con corpus real (>10 casos)?
  pytest tests/ml/test_regex_detector.py::test_detects_api_keys -v
```

---

## Troubleshooting

**Errores comunes y cómo resolverlos.**

### "Escribí código pero el test falla"

```
Causa típica: Código no cumple AC (Acceptance Criteria)

Solución:
1. Leer AC en ROADMAP §7 línea por línea
2. Verificar: qué exactamente dice que debe suceder
3. Leer el test que falla
4. Entender: ¿qué espera el test? ¿qué retorna mi código?
5. Corregir código

Nunca: "el test está mal, cambio el test"
```

### "¿Existe ya este código?"

```
Solución:
1. grep -r "nombre_de_funcion" apps/
2. Si encuentra algo:
   → Leer ese archivo
   → Entender qué hace
   → Usar eso, no reimplementar
3. Si no encuentra nada:
   → Procede a escribir
```

### "No sé qué AC tiene esta tarea"

```
Solución:
1. ROADMAP.md §7 - buscar por ID de tarea (ej: T1, T4, E2.1)
2. Leer la fila completa (Descripción + Criterio de aceptación)
3. Si sigue sin entender:
   → Leer el patrón técnico §5
   → Leer código existente similar (grep)
```

### "El test pasa pero siento que falta algo"

```
Solución:
1. Leer AC nuevamente, palabra por palabra
2. ¿El test cubre TODOS los AC?
   Ej: AC dice "test con 36 casos" → ¿test tiene 36 casos?
3. Si falta: agregar más tests
4. Nunca: "parece suficiente"
```

### "Necesito cambiar código existente que parece incorrecto"

```
Solución:
1. Grep: ¿está esta función cubierta por tests?
   ✓ Sí → el código funciona así a propósito. Leer test para entender por qué.
   ✗ No → agregar test primero, luego cambiar código.

Nunca: cambiar código solo porque "se ve mal"
```

### "Cambié X, pero no estoy seguro si rompí algo"

```
Solución:
1. Ejecutar TODOS los tests:
   pytest tests/ -v
   npm test
   
2. Si alguno falla:
   → Identifica cuál falla
   → Leer ese test
   → Entender qué esperaba
   → Corregir tu cambio

3. Nunca: "probablemente no importa"
```

---

## Changelog

**Historial de cambios a este documento.**

| Versión | Fecha | Cambio |
|---|---|---|
| 1.1.0 | 2026-05-23 | Patrones de seguridad (SoD, span-merging), E2E tests, OPA policy tests. Sincronizado con code review. |
| 1.0.0 | 2026-05-23 | Versión inicial. Estructura completa, patrones reales, límites claros. Sincronizado con ROADMAP.md §11. |

**Próxima revisión**: 2026-06-06 (cuando cierre la siguiente tarea en ROADMAP §7)  
**Responsable de mantener sincronizado**: Usuario

---

## Contacto y escalación

**Si algo no está cubierto en este documento:**

1. ¿Es sobre qué hacer? → ROADMAP.md §7 + AGENTS.md
2. ¿Es sobre cómo hacerlo? → SKILLS.md + §5 Patrones técnicos
3. ¿Es sobre decisión arquitectónica? → ADRs + DOC-0_UNIFIED.md
4. ¿Aún no está claro? → Leer AGENTS.md rol + principios
5. ¿Bloqueo o ambigüedad real? → Pedir confirmación explícita al usuario

**Nunca improvises. Consulta primero.**

---

*Last verified: 2026-05-23 · Align with ROADMAP.md on each phase closure*
