# SKILLS · SafeContext — Habilidades por dominio de agente
**Versión**: 1.0.0 · **Fecha**: 2026-05-25
**Uso**: Claude Code consulta este archivo antes de ejecutar tareas de cada dominio. Los sub-agentes reciben solo la sección de su dominio.
**Documentos relacionados**: [Manual 08 — Roles](manuals/08_ROLES_Y_PERMISOS.md), [Manual 06 — Guía Desarrollador](manuals/06_GUIA_DESARROLLADOR.md)

---

## SKILL-BACKEND · FastAPI + Workers + OPA

### Stack
- Python 3.14, FastAPI, asyncio, Pydantic v2
- Dramatiq + Redis broker
- OPA client (opa-python-client o HTTP directo)
- SQLAlchemy async + Alembic
- structlog para logs estructurados
- OpenTelemetry SDK para Python

### Patrones obligatorios

**Outbox pattern** (ADR-001):
```python
# SIEMPRE: primero escribir en outbox de PostgreSQL, luego encolar en Redis
async def dispatch_scan(operation_id: UUID, document: str):
    async with db.transaction():
        await db.execute(
            "INSERT INTO outbox (event_type, payload) VALUES ($1, $2)",
            'scan_requested',
            {'operation_id': str(operation_id), 'document_hash': sha256(document)}
        )
    # Solo después de commit exitoso en PG, encolar en Redis
    await broker.enqueue('scan', operation_id=str(operation_id))
```

**Trace propagation** (requerido en F1):
```python
from opentelemetry import trace
tracer = trace.get_tracer("safecontext.api")

@app.post("/v1/scan")
async def scan(request: ScanRequest):
    with tracer.start_as_current_span("scan") as span:
        trace_id = format(span.get_span_context().trace_id, '032x')
        span.set_attribute("artifact.digest", sha256(request.document))
        span.set_attribute("policy.version", request.policy_version)
        # ... resto del handler
```

**Interfaz de detector** (ADR-010):
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Finding:
    detector: str
    rule_id: str
    span_start: int
    span_end: int
    confidence: float
    severity: str
    explanation: dict

class DetectorInterface(ABC):
    @abstractmethod
    async def detect(self, text: str, policy: dict) -> list[Finding]:
        ...
```

**Worker idempotente** (ADR-007):
```python
@dramatiq.actor(max_retries=3, min_backoff=1000, max_backoff=30000)
async def process_scan(operation_id: str):
    # Verificar si ya fue procesado antes de actuar
    op = await db.get_operation(operation_id)
    if op.status != 'pending':
        return  # Idempotente: ya procesado
    # ... procesamiento
```

### Reglas críticas
- Nunca retornar un resultado sin `trace_id` en la respuesta
- Nunca usar `print()` — siempre `logger.info(...)` con structlog
- Nunca hardcodear umbrales de confianza — vienen de la política OPA
- Nunca modificar un artefacto almacenado en MinIO — crear nueva versión
- Toda excepción no controlada debe loguear `trace_id` y `operation_id`

### Tests requeridos por entregable
- Test unitario por cada clase de detector con corpus etiquetado
- Test de idempotencia para cada worker (re-entrega del mismo mensaje)
- Test de integración API → worker → DB con verificación de audit trail
- Test de política OPA con `opa test`

---

## SKILL-FRONTEND · Next.js + TypeScript + shadcn/ui

### Stack
- Next.js 16.2 (App Router), TypeScript estricto
- Tailwind CSS, shadcn/ui
- Custom cache handler (Redis) para multi-instancia
- Nginx como reverse proxy con TLS

### Patrones obligatorios

**Custom cache handler** (ADR-002, requerido desde F1):
```typescript
// cache-handler.ts — NUNCA usar caché en disco en multi-instancia
import { createClient } from 'redis'

const client = createClient({ url: process.env.REDIS_URL })

export default class RedisCache {
  async get(key: string) {
    const data = await client.get(key)
    return data ? JSON.parse(data) : null
  }
  async set(key: string, data: any, ctx: any) {
    const ttl = ctx.revalidate ?? 3600
    await client.setEx(key, ttl, JSON.stringify(data))
  }
  async revalidateTag(tag: string) {
    // invalidación por tag
  }
}
```

**Configuración en next.config.ts**:
```typescript
const nextConfig = {
  cacheHandler: require.resolve('./cache-handler'),
  cacheMaxMemorySize: 0, // deshabilitar caché en memoria
}
```

**No hay lógica de negocio en componentes**: los componentes invocan la API o el MCP Server. Nunca procesan documentos directamente.

### Sistema de diseño (evitar deuda de UI)
- Tokens de color, tipografía y spacing en `styles/tokens.ts` — no valores hardcodeados
- Componentes base en `components/base/` — wrappean shadcn/ui con tokens aplicados
- ADR de componentes: cada componente nuevo tiene su decisión documentada si no es trivial

### Reglas críticas
- Nunca usar `localStorage` o `sessionStorage` para datos de documentos
- Nunca mostrar trace_id o artifact_digest en UI pública sin control de acceso
- Toda llamada a API incluye manejo de error con mensaje estructurado al usuario
- TypeScript strict mode — 0 errores de tipo permitidos

---

## SKILL-DATA · PostgreSQL + Alembic + pgAudit

### Stack
- PostgreSQL 18.4, pgAudit
- SQLAlchemy async + Alembic para migraciones
- psycopg3 como driver

### Reglas de migración
```
NUNCA usar DROP sin respaldo verificado
NUNCA modificar columnas existentes sin migración backward-compatible
SIEMPRE nombrar índices explícitamente: idx_{tabla}_{columna}
SIEMPRE incluir rollback en cada migración Alembic
```

### RLS pattern (obligatorio desde F1):
```sql
-- Habilitar RLS en todas las tablas
ALTER TABLE operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE operations FORCE ROW LEVEL SECURITY;

-- Política base: tenant isolation
CREATE POLICY tenant_isolation ON operations
  USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Política de solo lectura para Viewer
CREATE POLICY viewer_readonly ON operations
  FOR SELECT
  USING (current_setting('app.current_role') IN ('viewer', 'reviewer', 'admin'));
```

### pgAudit (obligatorio desde F1):
```sql
-- En postgresql.conf
shared_preload_libraries = 'pgaudit'
pgaudit.log = 'write, ddl'
pgaudit.log_relation = on

-- Por tabla crítica
ALTER TABLE operations SET (security_barrier = true);
```

### Índices requeridos (F1):
```sql
CREATE INDEX CONCURRENTLY idx_operations_trace_id ON operations(trace_id);
CREATE INDEX CONCURRENTLY idx_operations_actor_id ON operations(actor_id);
CREATE INDEX CONCURRENTLY idx_findings_operation_id ON findings(operation_id);
CREATE INDEX CONCURRENTLY idx_artifacts_operation_id ON artifacts(operation_id);
CREATE INDEX CONCURRENTLY idx_outbox_processed ON outbox(processed) WHERE processed = false;
```

### Reglas críticas
- El agente DATA nunca ejecuta migraciones en producción sin revisión del agente principal
- Toda migración tiene un test que verifica el estado antes y después
- El schema de `operations` y `findings` es el contrato entre backend y data — cambios requieren versión

---

## SKILL-INFRA · Docker + Kubernetes + MinIO + OTel

### Stack
- Docker Compose (F1-F2), Kubernetes con CloudNativePG (F3+)
- MinIO con WORM + SSE
- OpenTelemetry Collector, Prometheus, Grafana

### Docker Compose — reglas
```yaml
# SIEMPRE: healthchecks en todos los servicios
# SIEMPRE: restart: unless-stopped en producción
# NUNCA: imagen :latest — siempre versión fijada
# NUNCA: secretos en environment directo — usar secrets de Compose o .env

services:
  api:
    image: safecontext/api:${VERSION}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    depends_on:
      postgres:
        condition: service_healthy
```

### MinIO — configuración obligatoria (F2):
```bash
# WORM / object locking — debe configurarse en creación del bucket
mc mb --with-lock minio/safecontext-artifacts

# Retención por defecto
mc retention set --default GOVERNANCE "30d" minio/safecontext-artifacts

# SSE con clave local (F2) o KMS (F4)
mc admin config set minio/ kes_config
```

### OTel Collector — pipeline mínimo:
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
  logging:
    loglevel: info

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging]
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

### Reglas críticas
- Ninguna imagen de producción contiene herramientas de desarrollo (pip install -e, npm dev deps)
- Dockerfiles multi-stage: builder + runtime minimal
- Trivy scan obligatorio en pipeline desde F1
- MinIO WORM verificado con test de intento de sobreescritura (debe fallar)

---

## SKILL-SECURITY · OIDC + Supply Chain + Secrets

### Stack
- Cosign (firma de imágenes)
- Syft (SBOM generation)
- Trivy (vulnerability scanning)
- GitHub OIDC para CI/CD (F3)
- External Secrets Operator + KMS (F4)

### GitHub Action — OIDC sin secretos estáticos (F3):
```yaml
permissions:
  id-token: write
  contents: read

jobs:
  build-and-sign:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Generate SBOM
        run: syft packages . -o spdx-json > sbom.json
      
      - name: Build image
        run: docker build -t safecontext/api:${{ github.sha }} .
      
      - name: Scan vulnerabilities
        run: trivy image --exit-code 1 --severity CRITICAL safecontext/api:${{ github.sha }}
      
      - name: Sign image with Cosign
        uses: sigstore/cosign-installer@v3
        run: |
          cosign sign --yes safecontext/api:${{ github.sha }}
      
      - name: Attach SBOM
        run: cosign attach sbom --sbom sbom.json safecontext/api:${{ github.sha }}
```

### Verificación en deploy gate:
```bash
# Verificar firma antes de deploy
cosign verify \
  --certificate-identity-regexp="https://github.com/safecontext/.*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  safecontext/api:${VERSION}

# Verificar SBOM
cosign verify-attestation \
  --type spdxjson \
  safecontext/api:${VERSION}
```

### Reglas críticas
- `detect-secrets` en pre-commit y en CI — 0 secretos en repositorio
- Toda imagen en producción tiene firma verificable antes del deploy
- SBOM adjunto a toda imagen — no opcional
- Ningún secreto estático en environment variables de CI

---

## SKILL-ML · Detectores + Evaluación

### Stack
- Microsoft Presidio (detección y anonimización de PII)
- spaCy (NLP, NER)
- Transformers / PyTorch (detectores custom)
- Corpus etiquetado para evaluación continua

### Interfaz de detector (implementar exactamente):
```python
# Implementación de referencia con Presidio
from presidio_analyzer import AnalyzerEngine
from safecontext.core.detector import DetectorInterface, Finding

class PresidioDetector(DetectorInterface):
    def __init__(self):
        self.engine = AnalyzerEngine()
    
    async def detect(self, text: str, policy: dict) -> list[Finding]:
        entities = policy.get('entities', ['EMAIL_ADDRESS', 'PHONE_NUMBER', 'PERSON'])
        results = self.engine.analyze(text=text, entities=entities, language='en')
        
        return [
            Finding(
                detector=f"presidio.{r.entity_type}",
                rule_id=f"presidio_{r.entity_type.lower()}",
                span_start=r.start,
                span_end=r.end,
                confidence=r.score,
                severity=self._severity_from_entity(r.entity_type),
                explanation={
                    "entity_type": r.entity_type,
                    "score": r.score,
                    "analysis_explanation": str(r.analysis_explanation)
                }
            )
            for r in results
        ]
```

### Evaluación de recall (requerida desde F1):
```python
# Corpus etiquetado mínimo en tests/fixtures/corpus/
# Formato: {text, expected_findings: [{detector, span_start, span_end, entity_type}]}

def evaluate_recall(detector, corpus):
    true_positives = 0
    false_negatives = 0
    
    for sample in corpus:
        findings = detector.detect(sample['text'], {})
        for expected in sample['expected_findings']:
            found = any(
                f.span_start == expected['span_start'] and
                f.detector.endswith(expected['entity_type'])
                for f in findings
            )
            if found:
                true_positives += 1
            else:
                false_negatives += 1
    
    recall = true_positives / (true_positives + false_negatives)
    return recall

# Gate: recall >= 0.90 en F1, >= 0.95 en F2, >= 0.98 en F5
```

### Reglas críticas
- Los modelos nunca se descargan en runtime — deben estar en la imagen o en volumen local
- El detector nunca modifica el texto original — solo genera findings
- Toda clase de entidad tiene al menos 10 ejemplos en el corpus de test
- Recall se mide en CI en cada PR que toca código de detector

---

---

## SKILL-ADMIN · Endpoints de administración (F6)

### Patrón: Endpoint admin protegido

```python
from core.auth_oidc import get_roles, require_auth
from fastapi import Depends, HTTPException, status
from typing import Annotated

_ADMIN_ROLE = "admin"

def _require_admin(payload: dict) -> None:
    if _ADMIN_ROLE not in get_roles(payload):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")

@router.post("/admin/mi-accion")
async def mi_accion(
    auth_payload: Annotated[dict, Depends(require_auth)],
    db: AsyncSession = Depends(get_db),
):
    _require_admin(auth_payload)
    # ... lógica
```

### Patrón: Múltiples roles permitidos

```python
_PRIVILEGED_ROLES = ("policy_editor", "admin")

def _require_privileged(payload: dict) -> None:
    roles = get_roles(payload)
    if not any(r in roles for r in _PRIVILEGED_ROLES):
        raise HTTPException(status_code=403, detail="Requires policy_editor or admin role")
```

### Patrón: Página admin (frontend)

```tsx
// Guard en layout — redirige si no es admin
const session = useSession();
if (!session?.roles.includes('admin')) redirect('/dashboard');

// Link condicional en NavBar
{hasRole('admin') && <Link href="/admin">Admin</Link>}

// Botón condicional por rol
const canReview = hasRole('reviewer') || hasRole('admin');
{canReview && <Button onClick={handleApprove}>Aprobar</Button>}
```

### Reglas críticas
- Solo existen 4 roles: `viewer`, `reviewer`, `policy_editor`, `admin`
- `platform_admin` fue eliminado — no usar
- Cada endpoint declara explícitamente qué roles acepta (sin herencia)
- SoD (check_self_approval) se aplica en approve, no en reject

---

## SKILL-MULTITENANCY · Multi-tenancy y aislamiento (F6)

### Patrón: Resolver tenant desde JWT

```python
from core.constants import DEFAULT_TENANT_ID

tenant_id_str = auth_payload.get("tenant_id", "")
tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else DEFAULT_TENANT_ID
```

### Patrón: Evaluación de política por tenant (OPA)

```python
# POST a OPA con tenant_config
response = await http_client.post(
    f"{OPA_URL}/v1/data/safecontext/policy/tenant_decision",
    json={
        "input": {
            "findings": findings,
            "waivers": active_waivers,
            "tenant_config": tenant.policy_config or {},
        }
    }
)
```

### Patrón: Quotas por tenant

```python
from core.quotas import check_daily_scan_quota, check_document_size, check_tenant_rate_limit

# Verificar antes de procesar
check_document_size(body.document, tenant.max_document_size)
await check_daily_scan_quota(tenant_id, tenant.max_scans_per_day, request)
check_tenant_rate_limit(tenant_id, tenant.rate_limit_rpm)
```

### Reglas críticas
- RLS se configura por migración `0009_rls.py` — no tocar sin revisar impacto
- DEFAULT_TENANT_ID = `00000000-0000-0000-0000-000000000000`
- chain_hash es per-tenant — no mezclar cadenas entre tenants
- Los certificados de borrado se almacenan bajo path `{tenant_id}/deletion-certificates/`

---

*Consultar este archivo antes de ejecutar cualquier tarea del dominio correspondiente.*
*Para la matriz completa de permisos, ver Manual 08. Para ambigüedades, escalar al agente principal.*
