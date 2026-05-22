# SafeContext — Guía del Desarrollador
**Versión**: 1.0.0 | **Fecha**: 2026-05-18 | **Audiencia**: Desarrolladores que mantienen, extienden o escalan SafeContext

> Este documento responde a *cómo trabajar* con el código. Para entender *qué hace* cada componente, ver `01_ARQUITECTURA_TECNICA.md`.

---

## Tabla de contenidos

1. [Setup del entorno de desarrollo](#1-setup-del-entorno-de-desarrollo)
2. [Flujo de trabajo diario](#2-flujo-de-trabajo-diario)
3. [Estructura del código](#3-estructura-del-código)
4. [Cómo agregar una feature](#4-cómo-agregar-una-feature)
5. [Cómo corregir un bug](#5-cómo-corregir-un-bug)
6. [Testing](#6-testing)
7. [Debugging — trazar un request de punta a punta](#7-debugging--trazar-un-request-de-punta-a-punta)
8. [Manejo de dependencias](#8-manejo-de-dependencias)
9. [Convenciones de código](#9-convenciones-de-código)
10. [Escalado](#10-escalado)
11. [Proceso de release](#11-proceso-de-release)

---

## 1. Setup del entorno de desarrollo

### Requisitos previos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Docker Desktop | 24+ | `docker --version` |
| Python | 3.14 | `python --version` |
| Node.js | 24.16.0 | `node --version` |
| Git | 2.40+ | `git --version` |

### Primeros pasos (desde cero)

```bash
# 1. Clonar el repositorio
git clone https://github.com/oscarives/safeContext.git
cd safeContext

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env — los valores de desarrollo ya son válidos por defecto

# 3. Instalar pre-commit hooks (obligatorio antes del primer commit)
pip install pre-commit
pre-commit install

# 4. Verificar que los hooks funcionan
pre-commit run --all-files

# 5. Construir las imágenes Docker (primera vez: ~15 min — descarga spaCy en_core_web_lg)
docker compose build

# 6. Levantar el stack completo
docker compose up -d

# 7. Aplicar migraciones de base de datos
docker compose exec api alembic upgrade head

# 8. Verificar que todo está healthy
curl http://localhost:8000/health
# Esperado: {"status":"ok","postgres":"ok","redis":"ok","minio":"ok"}
```

### Verificación de entorno completo

```bash
# Todos los servicios deben estar healthy
docker compose ps

# Scan de prueba
curl -s -X POST http://localhost:8000/v1/scan \
  -H "Authorization: Bearer $(grep MCP_AUTH_TOKEN .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"document": "test@example.com", "policy_name": "base"}' | python -m json.tool
```

---

## 2. Flujo de trabajo diario

### Arrancar el stack

```bash
docker compose up -d          # levantar todos los servicios
docker compose logs -f api    # seguir logs de la API en tiempo real
docker compose logs -f worker # seguir logs de los workers
```

### Parar el stack

```bash
docker compose down           # para y elimina contenedores (datos persisten en volúmenes)
docker compose down -v        # ⚠️ elimina también los volúmenes (borra la BD)
```

### Reiniciar un servicio tras cambios en el código

```bash
# Reconstruir y reiniciar solo la API (evita reconstruir worker con spaCy)
docker compose build api && docker compose up -d api

# Reiniciar sin rebuild (solo si el código se copió pero la imagen no cambió)
docker compose restart api
```

### Ver métricas en tiempo real

```bash
# Prometheus
open http://localhost:9090

# Grafana (admin/admin)
open http://localhost:3001

# Métricas raw de la API
curl http://localhost:8000/metrics/ | grep safecontext_
```

### Correr tests

```bash
# Tests de API (rápidos, no requieren stack levantado)
cd apps/api && python -m pytest tests/ -v

# Tests de recall ML (requieren worker con modelos)
docker compose exec worker python -m pytest workers/tests/ml/test_recall.py -v --no-header

# Tests OPA (require docker)
docker run --rm -v "$(pwd)/policies:/policies:ro" \
  openpolicyagent/opa:1.4.0 test /policies/ -v --coverage
```

---

## 3. Estructura del código

```
safeContext/
├── apps/
│   ├── api/                    # FastAPI backend + MCP Server
│   │   ├── main.py             # Entrypoint: app, lifespan, routers, /metrics
│   │   ├── config.py           # Pydantic Settings (todas las vars de entorno)
│   │   ├── api/v1/             # Endpoints REST
│   │   │   ├── scan.py         # POST /v1/scan
│   │   │   ├── audit.py        # GET /v1/audit/{trace_id}
│   │   │   ├── review.py       # GET+POST /v1/review/*
│   │   │   └── health.py       # GET /health
│   │   ├── mcp/                # MCP Server
│   │   │   ├── router.py       # Todos los tools MCP + dispatch versionado
│   │   │   ├── tools.py        # Definición JSON de schemas de tools
│   │   │   ├── schemas.py      # Pydantic models para MCP
│   │   │   └── auth.py         # Bearer token + rate limiting
│   │   ├── core/               # Utilidades transversales
│   │   │   ├── tracing.py      # OTel setup + get_trace_id()
│   │   │   ├── metrics.py      # Gauges/Counters/Histograms Prometheus
│   │   │   ├── logging.py      # structlog JSON renderer
│   │   │   ├── ports.py        # BrokerPort interface (ADR-011)
│   │   │   └── auth_oidc.py    # OIDC middleware + rate limiting
│   │   ├── adapters/
│   │   │   └── redis_broker.py # ÚNICA clase que importa redis en la API
│   │   ├── db/
│   │   │   ├── models/         # SQLAlchemy ORM models (5 tablas)
│   │   │   ├── migrations/     # Alembic migrations
│   │   │   │   └── versions/   # 0001_initial_schema.py, 0002_...
│   │   │   ├── session.py      # AsyncSession factory
│   │   │   └── base.py         # DeclarativeBase
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── conftest.py         # Fixtures globales de tests
│   │   └── tests/              # Tests unitarios (sin infraestructura real)
│   │       ├── api/            # Tests de endpoints REST
│   │       ├── db/             # Tests de schema/modelos
│   │       └── mcp/            # Tests de tools MCP
│   └── ui/                     # Next.js frontend
│       ├── src/app/            # App Router pages
│       │   ├── dashboard/      # /dashboard
│       │   ├── review/         # /review (hallazgos escalados)
│       │   ├── audit/          # /audit (búsqueda por trace_id)
│       │   └── login/          # /login (SSO Keycloak)
│       ├── src/lib/            # api-client.ts
│       ├── cache-handler.js    # Redis cache handler (multi-instancia)
│       └── next.config.js      # Config Next.js
│
├── workers/                    # Dramatiq workers (proceso separado)
│   ├── main.py                 # Entrypoint: broker, background tasks, signals
│   ├── db.py                   # AsyncSession factory propia (loop independiente)
│   ├── outbox_relay.py         # Loop: PostgreSQL outbox → Redis (ADR-001)
│   ├── dlq_monitor.py          # Gauge safecontext_dlq_depth
│   ├── core/
│   │   ├── ports.py            # BrokerPort, StoragePort, CachePort (ADR-011)
│   │   ├── detector.py         # DetectorInterface + Finding dataclass
│   │   ├── metrics.py          # Prometheus metrics para workers
│   │   └── opa_client.py       # Cliente OPA con hot-reload
│   ├── adapters/
│   │   ├── redis_broker.py     # ÚNICA clase que importa redis en workers
│   │   └── s3_storage.py       # ÚNICA clase que importa boto3
│   ├── agents/                 # Un archivo por agente interno
│   │   ├── detector_agent.py   # @dramatiq.actor — detección Presidio
│   │   ├── sanitizer_agent.py  # @dramatiq.actor — redacción
│   │   ├── classifier_agent.py # @dramatiq.actor — clasificación
│   │   ├── auditor_agent.py    # @dramatiq.actor — upload a MinIO
│   │   └── reviewer_agent.py   # @dramatiq.actor — registro de escalación
│   └── ml/
│       ├── presidio_detector.py  # PresidioDetector(DetectorInterface)
│       ├── model_loader.py       # Carga modelos desde /models (air-gapped)
│       └── recall_evaluator.py   # Evalúa recall y setea Prometheus gauge
│
├── policies/
│   └── base/
│       ├── safecontext.rego      # Política principal OPA
│       ├── safecontext_test.rego # Tests OPA (mismo package)
│       └── metadata.json         # policy_version semver
│
├── infra/
│   ├── compose/                # Configs para Docker Compose
│   │   ├── nginx-dev.conf      # nginx HTTP para desarrollo
│   │   ├── prometheus.yml      # Scrape config
│   │   ├── prometheus-alerts.yml
│   │   ├── prometheus-slo-rules.yml
│   │   ├── otel-collector.yaml
│   │   ├── keycloak/           # Realm export para SSO
│   │   ├── vault/              # Scripts init KMS
│   │   └── postgres/           # pgAudit init + backup scripts
│   ├── k8s/                    # Manifiestos Kubernetes (F3+)
│   └── github-action/          # GitHub Action oficial
│
├── docs/
│   ├── adr/                    # ADR-001 a ADR-011
│   ├── manuals/                # Esta carpeta
│   ├── runbooks/               # DR, DLQ, key-rotation, models
│   └── drills/                 # Plantillas de evidencia de drills
│
├── docker-compose.yml          # Stack completo (14 servicios)
├── .env.example                # Plantilla de variables (sin valores reales)
├── .pre-commit-config.yaml     # detect-secrets, ruff, mypy, eslint
└── .secrets.baseline           # Baseline de detect-secrets (0 hallazgos)
```

---

## 4. Cómo agregar una feature

### 4.1 Nuevo endpoint REST

**Ejemplo**: añadir `GET /v1/stats` con estadísticas de operaciones.

```bash
# 1. Crear el archivo del endpoint
# apps/api/api/v1/stats.py

# 2. Registrar en el router
# apps/api/api/v1/router.py → v1_router.include_router(stats.router)

# 3. Añadir schema de respuesta si hace falta
# apps/api/schemas/stats.py

# 4. Escribir el test (sin BD real — usar dependency_overrides)
# apps/api/tests/api/test_stats.py

# 5. Verificar
cd apps/api && python -m pytest tests/api/test_stats.py -v
```

**Reglas obligatorias para endpoints nuevos**:
- `Depends(require_mcp_token)` — autenticación Bearer en todos los endpoints
- `trace_id` en la respuesta si la operación genera registro
- structlog en cada acción: `log.info("stats.queried", count=n)`
- OTel span: `with tracer.start_as_current_span("stats.query"):`

---

### 4.2 Nuevo tool MCP

**Ejemplo**: añadir `safecontext.redact.preview` (vista previa sin guardar).

```python
# Paso 1: Añadir schema en apps/api/mcp/tools.py → MCP_TOOLS list
{
    "name": "safecontext.redact.preview",
    "version": "1.2.0",        # nueva versión minor
    "description": "...",
    "input_schema": {...},
    "output_schema": {...},
}

# Paso 2: Añadir handler en apps/api/mcp/router.py
@router.post("/tools/safecontext.redact.preview", response_model=MCPToolResult)
async def tool_redact_preview(request: RedactPreviewRequest, ...):
    ...

# Paso 3: Añadir al VERSION_COMPAT en router.py
("safecontext.redact.preview", "1.2.0"): "tool_redact_preview",

# Paso 4: Actualizar CURRENT_VERSION = "1.2.0"

# Paso 5: Tests en apps/api/tests/mcp/
```

**Regla clave**: nueva funcionalidad = nueva versión minor (1.1.0 → 1.2.0). Breaking change = versión major.

---

### 4.3 Nuevo agente interno (worker)

**Ejemplo**: añadir un `TranslatorAgent` que traduce el documento antes del scan.

```python
# Paso 1: Crear workers/agents/translator_agent.py
import dramatiq
from workers.main import broker  # reutiliza el broker configurado

@dramatiq.actor(
    queue_name="safecontext_translate",
    max_retries=3,
    min_backoff=1000,
    max_backoff=30000,
)
def process_translate(operation_id: str) -> None:
    import asyncio
    asyncio.run(_process_translate_async(operation_id))

async def _process_translate_async(operation_id: str) -> None:
    # 1. Idempotencia PRIMERO
    async with get_session() as session:
        op = await session.get(Operation, operation_id)
        if op.status != "pending":
            return  # ya procesado

    # 2. Lógica de negocio
    # ...

    # 3. Encolar siguiente agente
    from workers.agents.detector_agent import process_scan
    process_scan.send(operation_id)
```

```python
# Paso 2: Añadir al outbox_relay.py
_EVENT_TO_QUEUE["translate_requested"] = "safecontext_translate"

def _get_actor(queue_name):
    ...
    "safecontext_translate": process_translate,  # añadir aquí
    ...

# Paso 3: Importar en workers/main.py para que Dramatiq lo registre
# CMD del Dockerfile: añadir workers.agents.translator_agent

# Paso 4: Test de idempotencia en workers/tests/workers/
```

---

### 4.4 Nueva regla OPA

**Ejemplo**: añadir bloqueo para documentos con más de 5 hallazgos de cualquier tipo.

```rego
# En policies/base/safecontext.rego

# Nueva regla: bloquear si hay demasiados hallazgos
too_many_findings(findings) if {
    count(findings) > 5
}
```

```rego
# En policies/base/safecontext_test.rego (MISMO package)

test_too_many_findings_blocks if {
    findings := [
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
    ]
    too_many_findings(findings)
}
```

```bash
# Verificar tests OPA
docker run --rm -v "$(pwd)/policies:/policies:ro" \
  openpolicyagent/opa:1.4.0 test /policies/ -v

# OPA hot-reload: sin restart — el worker lo recoge en 30s
```

```json
// Actualizar policies/base/metadata.json
{ "version": "1.1.0" }
```

---

### 4.5 Cambio de schema de base de datos (migración)

**Regla crítica**: toda migración debe tener `upgrade()` Y `downgrade()`.

```bash
# Paso 1: Modificar el modelo SQLAlchemy
# apps/api/db/models/operation.py → añadir campo

# Paso 2: Generar la migración
cd apps/api
DATABASE_URL="postgresql+asyncpg://safecontext_app:PASSWORD@localhost:5432/safecontext" \
  alembic revision --autogenerate -m "add_field_to_operations"

# Paso 3: Revisar el archivo generado en db/migrations/versions/
# ⚠️ SIEMPRE revisar el autogenerate — puede generar DROP innecesarios

# Paso 4: Añadir downgrade() si está vacío
def downgrade() -> None:
    op.drop_column("operations", "nuevo_campo")

# Paso 5: Aplicar en desarrollo
docker compose exec api alembic upgrade head

# Paso 6: Verificar rollback
docker compose exec api alembic downgrade -1
docker compose exec api alembic upgrade head  # volver a aplicar

# Paso 7: Test que verifica el schema
# apps/api/tests/db/test_schema.py → añadir verificación del nuevo campo
```

**Nombrado de migraciones**:
- `0003_add_tenant_id_to_operations.py`
- `0004_add_index_findings_detector.py`
- Siempre número secuencial + descripción clara.

---

## 5. Cómo corregir un bug

### Proceso estándar

```
1. Reproducir el bug localmente
   → docker compose up -d
   → Reproducir el caso exacto con curl o pytest

2. Identificar el trace_id del error
   → docker compose logs api | grep "error"
   → Buscar el trace_id en los logs

3. Trazar el flujo completo con el trace_id
   → SELECT * FROM operations WHERE trace_id = 'X';
   → SELECT * FROM findings WHERE operation_id = (id de arriba);
   → docker compose logs worker | grep "trace_id=X"

4. Escribir un test que reproduce el bug ANTES de corregirlo
   → El test debe FALLAR con el bug presente
   → Confirma que entendiste el bug

5. Corregir el código

6. Verificar que el test pasa

7. Correr la suite completa
   → cd apps/api && python -m pytest tests/ -v
   → Ningún test regresión

8. Commit con formato:
   → "fix(scope): descripción corta del bug"
   → "Fixes: descripción del comportamiento incorrecto"
   → "Root cause: descripción de la causa"
```

### Bugs frecuentes y su localización

| Síntoma | Dónde buscar | Causa probable |
|---|---|---|
| `scan` retorna 0 findings siempre | `docker compose logs worker` | `document_text` no en outbox payload |
| Worker no procesa mensajes | `outbox_relay.py` logs | event_type no mapeado en `_EVENT_TO_QUEUE` |
| 500 en endpoint MCP | Falta `await db.begin()` en mock | `db.begin()` no configurado como async ctx manager |
| `policy_version: v0.0.0` | `apps/api/api/v1/scan.py` | Path OPA incorrecto |
| `Future attached to different loop` | `workers/db.py` | Engine creado en loop diferente al del worker |
| `ModuleNotFoundError: No module named 'db'` | `workers/Dockerfile` | `COPY apps/api/db/ ./db/` faltante |
| `detector_recall` = 0 en Prometheus | `workers/ml/recall_evaluator.py` | Loop no arrancado o corpus no encontrado |

---

## 6. Testing

### Pirámide de tests

```
              /──────────────\
             /  E2E (manual)  \      docker compose up + curl
            /──────────────────\
           /  Integración (PG)  \    pytest con BD real en CI
          /──────────────────────\
         /   Unitarios (mocks)    \  pytest con dependency_overrides
        /────────────────────────────\
```

### Cómo escribir un test de endpoint

```python
# apps/api/tests/api/test_nuevo_endpoint.py
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, MagicMock
from main import app

# Fixture estándar — reutilizar este patrón
@pytest.fixture(autouse=True)
def override_db():
    from db.session import get_db

    async def _fake_db():
        session = AsyncMock()
        # Configurar begin() como async context manager
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=None)
        cm.__aexit__ = AsyncMock(return_value=False)
        session.begin = MagicMock(return_value=cm)
        session.add = MagicMock()
        yield session

    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_nuevo_endpoint_returns_200():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-token"}
    ) as client:
        resp = await client.get("/v1/nuevo")
    assert resp.status_code == 200
```

### Cómo escribir un test de worker

```python
# workers/tests/workers/test_nuevo_agent.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_idempotencia_nuevo_agent():
    """Re-enviar el mismo operation_id no debe duplicar resultados."""
    mock_op = MagicMock()
    mock_op.status = "completed"  # ya procesado

    with patch("workers.agents.nuevo_agent.get_session") as mock_session:
        mock_session.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(
            get=AsyncMock(return_value=mock_op)
        ))
        # Ejecutar 2 veces
        await _process_nuevo_async("op-id-123")
        await _process_nuevo_async("op-id-123")
        # No debe haber procesamiento adicional — mock no llamado
```

### Correr tests con cobertura

```bash
cd apps/api
python -m pytest tests/ --cov=. --cov-report=term-missing --cov-fail-under=80
```

---

## 7. Debugging — trazar un request de punta a punta

### Herramienta: trace_id

Todo request genera un `trace_id` UUID. Con él puedes seguir el flujo completo:

```bash
# 1. Hacer el scan y capturar el trace_id
TRACE=$(curl -s -X POST http://localhost:8000/v1/scan \
  -H "Authorization: Bearer $(grep MCP_AUTH_TOKEN .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"document": "test@example.com", "policy_name": "base"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['trace_id'])")

echo "trace_id: $TRACE"

# 2. Ver el estado en PostgreSQL
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT status, policy_version, artifact_digest FROM operations WHERE trace_id='$TRACE';"

# 3. Ver los findings
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT detector, severity, confidence FROM findings f
      JOIN operations o ON f.operation_id=o.id
      WHERE o.trace_id='$TRACE';"

# 4. Ver en los logs del worker
docker compose logs worker | grep "$TRACE"

# 5. Ver las redacciones aplicadas
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT redaction_type, policy_version FROM redactions r
      JOIN operations o ON r.operation_id=o.id
      WHERE o.trace_id='$TRACE';"

# 6. Ver el artefacto en MinIO
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT artifact_type, minio_key, worm_locked FROM artifacts a
      JOIN operations o ON a.operation_id=o.id
      WHERE o.trace_id='$TRACE';"
```

### Ver outbox pendientes (mensajes no procesados)

```bash
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT id, event_type, created_at FROM outbox WHERE processed=false ORDER BY created_at;"
```

### Ver DLQ (mensajes fallidos)

```bash
docker compose exec redis redis-cli LRANGE dramatiq:safecontext_dl 0 -1
```

### Consultar OPA directamente

```bash
# Ver política activa
curl http://localhost:8181/v1/data/safecontext/policy/policy_version

# Evaluar una decisión
curl -X POST http://localhost:8181/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "x := data.safecontext.policy.decision([{\"entity_type\": \"API_KEY\", \"confidence\": 0.98, \"severity\": \"critical\"}])", "input": {}}'
```

---

## 8. Manejo de dependencias

### Añadir dependencia Python (API o workers)

```bash
# 1. Añadir a requirements.txt del módulo correspondiente
echo "nueva-libreria>=1.0.0" >> apps/api/requirements.txt

# 2. Rebuild de la imagen
docker compose build api

# 3. Verificar que no hay conflictos
docker compose exec api python -c "import nueva_libreria; print('ok')"
```

**Regla**: nunca usar `latest` ni sin versión fija. Siempre `>=X.Y.Z`.

### Añadir dependencia Node.js (UI)

```bash
# Modificar apps/ui/package.json directamente
# Luego rebuild
docker compose build ui
```

### Actualizar spaCy/Presidio (modelos ML)

Ver `docs/runbooks/model-update.md` — proceso especial para no romper air-gapped.

---

## 9. Convenciones de código

### Python (API y Workers)

```python
# ✅ Correcto: structlog siempre, nunca print()
log = structlog.get_logger()
log.info("scan.started", trace_id=str(trace_id), document_size=len(doc))

# ❌ Incorrecto
print(f"scan started: {trace_id}")

# ✅ Correcto: trace_id en TODA respuesta de operación
return ScanResponse(trace_id=trace_uuid, ...)

# ❌ Incorrecto: respuesta sin trace_id
return {"findings": findings}

# ✅ Correcto: worker idempotente SIEMPRE
if op.status != "pending":
    return  # ya procesado — idempotencia

# ❌ Incorrecto: procesar sin verificar estado previo
findings = await detector.detect(doc, policy)

# ✅ Correcto: outbox pattern (PG antes de Redis)
async with db.begin():
    db.add(operation)
    db.add(outbox_event)
# SOLO después del commit:
await broker.enqueue(...)

# ❌ Incorrecto: encolar antes del commit
await broker.enqueue(...)
await db.commit()

# ✅ Correcto: BrokerPort, no redis directamente (ADR-011)
from core.ports import BrokerPort
async def dispatch(broker: BrokerPort, ...):

# ❌ Incorrecto: import redis directo fuera del adapter
import redis  # solo en redis_broker.py
```

### Commits

```
feat(scope): descripción corta en presente
fix(scope): descripción del bug corregido
test(scope): añadir tests para X
docs(scope): actualizar manual Y
refactor(scope): descripción sin cambio de comportamiento
chore(scope): cambios de configuración/herramientas

Cuerpo (opcional): contexto adicional
Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

### Nombres

| Elemento | Convención | Ejemplo |
|---|---|---|
| Tabla BD | snake_case plural | `operations`, `findings` |
| Índice BD | `idx_{tabla}_{columna}` | `idx_operations_trace_id` |
| Worker actor | `process_{nombre}` | `process_scan`, `process_audit` |
| Queue name | `safecontext_{nombre}` | `safecontext_scan` |
| Métrica Prometheus | `safecontext_{nombre}_{unidad}` | `safecontext_scan_duration_seconds` |
| Tool MCP | `safecontext.{nombre}` | `safecontext.scan` |
| Migración Alembic | `{N:04d}_{descripcion}.py` | `0003_add_tenant_id.py` |

---

## 10. Escalado

### Cuándo escalar cada componente

| Síntoma | Componente a escalar | Cómo |
|---|---|---|
| Latencia p95 de API > 1s | API | `docker compose up -d --scale api=3` |
| DLQ crece / workers lentos | Workers | `docker compose up -d --scale worker=4` |
| PG con CPU > 80% | PostgreSQL | Migrar a CloudNativePG en K8s con réplicas |
| MinIO sin espacio | MinIO | Añadir volumen o migrar a cluster MinIO |
| Redis saturado | Redis | Aumentar `maxmemory` en config |

### Escalar workers en Docker Compose

```bash
# Escalar a 3 instancias de worker (cada una con 2 procesos Dramatiq)
docker compose up -d --scale worker=3

# Verificar que todas están consumiendo del queue
docker compose logs worker | grep "Worker process is ready"
```

### Migrar a Kubernetes

Los manifiestos están en `infra/k8s/`. Para aplicarlos:

```bash
# 1. Configurar kubeconfig
kubectl config use-context mi-cluster

# 2. Crear namespace
kubectl apply -f infra/k8s/namespace.yaml

# 3. Crear secrets (NO commitear valores reales)
kubectl create secret generic safecontext-secrets \
  --from-env-file=.env -n safecontext

# 4. Aplicar todos los manifiestos
kubectl apply -k infra/k8s/

# 5. Verificar HPA
kubectl get hpa -n safecontext

# 6. Aplicar migraciones
kubectl exec -n safecontext deploy/api -- alembic upgrade head
```

### Ajustar umbrales de recall y detección

```bash
# Los umbrales viven en policies/base/safecontext.rego
# Cambiar y OPA recarga automáticamente en 30 segundos (hot-reload)

# Verificar recall actual
curl http://localhost:9090/api/v1/query?query=safecontext_detector_recall
```

---

## 11. Proceso de release

### Flujo completo

```
1. Feature branch
   git checkout -b feat/nombre-feature

2. Desarrollo + tests
   cd apps/api && python -m pytest tests/ -v
   pre-commit run --all-files

3. Pull Request a main
   - CI corre automáticamente: lint + tests + OPA + SafeContext gate
   - Review de código requerido

4. Merge a main
   - build-sign.yml corre: SBOM + Cosign + SLSA
   - Imágenes publicadas en GHCR con SHA del commit

5. Deploy
   - deploy.yml requiere aprobador humano (GitHub environment: production)
   - Trivy scan final → aprobador → kubectl rollout
```

### Actualizar policy_version

```bash
# 1. Modificar policies/base/safecontext.rego
policy_version := "1.1.0"

# 2. Actualizar policies/base/metadata.json
{ "version": "1.1.0" }

# 3. Correr tests OPA
docker run --rm -v "$(pwd)/policies:/policies:ro" \
  openpolicyagent/opa:1.4.0 test /policies/ -v

# 4. Las políticas se despliegan INDEPENDIENTEMENTE del release de la app
# OPA hot-reload las recoge en 30 segundos sin reinicio
```

### Rollback de emergencia

```bash
# Docker Compose
docker compose up -d --scale api=0  # detener
# Cargar imagen anterior
docker tag safecontext/api:COMMIT_ANTERIOR safecontext/api:dev
docker compose up -d api

# Kubernetes
kubectl rollout undo deployment/api -n safecontext
kubectl rollout status deployment/api -n safecontext
```

### Rollback de migración de BD

```bash
# ⚠️ Solo si el release incluye migraciones reversibles
docker compose exec api alembic downgrade -1
# Verificar: docker compose exec api alembic current
```

---

## Apéndice: atajos útiles

```bash
# Ver todas las operaciones recientes
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT trace_id, status, created_at FROM operations ORDER BY created_at DESC LIMIT 10;"

# Limpiar datos de desarrollo (resetear BD)
docker compose down -v && docker compose up -d
docker compose exec api alembic upgrade head

# Ver métricas de recall en Prometheus
curl -s "http://localhost:9090/api/v1/query?query=safecontext_detector_recall" \
  | python -c "import json,sys; r=json.load(sys.stdin)['data']['result']; [print(f'{x[\"metric\"][\"class\"]}: {float(x[\"value\"][1]):.3f}') for x in r]"

# Forzar re-evaluación de recall (sin esperar 5 min)
docker compose restart worker

# Verificar que no hay secretos en el repo
detect-secrets scan --baseline .secrets.baseline

# Ver log de OPA (hot-reload)
docker compose logs opa | grep "policy"
```
