# PLAN DE VALIDACIÓN POR FASES — SafeContext
## Para Pruebas Incrementales con Clientes Reales

**Versión**: 1.0  
**Fecha**: 2026-05-28  
**Objetivo**: Validar SafeContext fase por fase, abriendo cada componente a clientes reales cuando pase su gate de salida

---

## ESTRUCTURA DEL PLAN

```
FASE 0: Health & Foundation
  ├─ Gate de Salida: Todos los servicios healthy, tests existentes pasen
  └─ Apto para: QA interno, validación técnica

FASE 1: Core Tests & Existing Suite
  ├─ Gate de Salida: 100% de tests backend pasando, 90%+ frontend
  └─ Apto para: Clientes técnicos (evaluadores)

FASE 2: Multi-Tenancy (Aislamiento)
  ├─ Gate de Salida: RLS, quotas, audit trail funcionan con 2 tenants reales
  └─ Apto para: Primeros clientes (máx 2-3 empresas)

FASE 3: Chain of Custody (Criptografía)
  ├─ Gate de Salida: TSA, chain_hash, signatures, WORM verificados
  └─ Apto para: Clientes con requisitos de compliance legal

FASE 4: Compliance & GDPR
  ├─ Gate de Salida: GDPR purge, SIEM, compliance reports funcionan
  └─ Apto para: Clientes sujetos a regulaciones (GDPR, SOC2, HIPAA)

FASE 5: Security & Admin Module
  ├─ Gate de Salida: OIDC, RBAC, SoD, admin CRUD funcionan end-to-end
  └─ Apto para: Clientes empresariales con múltiples usuarios/roles

FASE 6: Observability & Load
  ├─ Gate de Salida: Traces end-to-end, métricas, load SLAs cumplidas
  └─ Apto para: Despliegue a producción general
```

---

## FASE 0: Health & Foundation

**Duración Estimada**: 1-2 horas  
**Responsable**: QA Interno  
**Artefactos**: Health check report

### Objetivos
- ✅ Docker stack levantado y saludable
- ✅ Todos los endpoints /health respondiendo
- ✅ Base de datos inicializada
- ✅ Servicios principales accesibles

### Criterios de Aceptación

```
[ ] Docker Compose levantado con --profile full
[ ] 12/12 servicios en status "healthy"
[ ] curl http://localhost:8000/health → 200 OK
[ ] curl http://localhost:3000 → 200 OK (UI)
[ ] curl http://localhost:9090 → 200 OK (Prometheus)
[ ] curl http://localhost:8080/realms/safecontext → 200 OK (Keycloak)
[ ] PostgreSQL: pg_isready → accepting connections
[ ] Redis: redis-cli ping → PONG
[ ] OPA: /data/safecontext/policy/policy_version → evaluable
[ ] MinIO: buckets created, Object Lock enabled
```

### Ejecución

```bash
# 1. Levantar Docker
docker compose --profile auth --profile full up -d

# 2. Esperar health checks
docker compose ps
# Todos deben estar en "healthy" o "running"

# 3. Verificar endpoints críticos
curl http://localhost:8000/health
curl http://localhost:3000
curl http://localhost:8080/realms/safecontext

# 4. Generar reporte
docker compose ps > /tmp/FASE0-docker-status.txt
curl http://localhost:8000/health > /tmp/FASE0-health-check.txt
```

### Gate de Salida
- ✅ Reporte `/tmp/FASE0-docker-status.txt` con 12/12 servicios healthy
- ✅ Reporte `/tmp/FASE0-health-check.txt` con status 200

**Si PASA FASE 0**: Proceder a FASE 1  
**Si FALLA FASE 0**: Revisar logs de Docker, diagnosticar servicio fallido

---

## FASE 1: Core Tests & Existing Suite

**Duración Estimada**: 2-3 horas  
**Responsable**: QA Técnico  
**Artefactos**: Test results JSON, coverage reports

### Objetivos
- ✅ Frontend tests (112) pasan ≥90%
- ✅ Backend API tests (259) pasan 100%
- ✅ OPA policy tests pasan
- ✅ No hay regresiones

### Criterios de Aceptación

```
FRONTEND:
  [ ] npm test pasa con ≥90% (112 tests)
  [ ] Reporte: /tmp/FASE1-frontend-results.json
  
BACKEND API:
  [ ] pytest tests/ pasa 100% (259+ tests)
  [ ] Reporte: /tmp/FASE1-backend-results.json
  [ ] Coverage ≥80%
  
OPA POLICIES:
  [ ] opa test /policies pasa todos los tests
  [ ] Reporte: /tmp/FASE1-opa-results.txt
```

### Ejecución

```bash
# 1. Frontend tests
cd apps/ui
npm test -- --testPathIgnorePatterns=e2e 2>&1 | tee /tmp/FASE1-frontend-results.log
# Validar: "Tests: X passed"

# 2. Backend API tests
cd apps/api
pytest tests/ -v --tb=short --json=/tmp/FASE1-backend-results.json 2>&1 | tee /tmp/FASE1-backend-results.log
# Validar: "passed" = 259+

# 3. OPA tests
docker compose exec opa opa test /policies -v 2>&1 | tee /tmp/FASE1-opa-results.txt
# Validar: todos los tests pasan

# 4. Summary
echo "FASE 1 RESULTS:" > /tmp/FASE1-SUMMARY.txt
grep -E "Tests:.*passed|passed.*in" /tmp/FASE1-frontend-results.log >> /tmp/FASE1-SUMMARY.txt
grep -E "passed.*in" /tmp/FASE1-backend-results.log >> /tmp/FASE1-SUMMARY.txt
```

### Gate de Salida
- ✅ Frontend: ≥90% pass rate (≥101/112 tests)
- ✅ Backend: 100% pass rate (259/259 tests)
- ✅ OPA: 100% pass rate

**Si PASA FASE 1**: Proceder a FASE 2  
**Si FALLA FASE 1**: Identificar tests fallidos, hacer bugfix, re-run

---

## FASE 2: Multi-Tenancy (Aislamiento)

**Duración Estimada**: 3-4 horas  
**Responsable**: QA Funcional + Dev  
**Artefactos**: Test suite, tenant isolation report, audit logs

### Objetivos
- ✅ Crear 2 tenants reales en BD
- ✅ Validar RLS aislamiento (datos no se mezclan)
- ✅ Validar quotas per-tenant
- ✅ Validar audit trail segregado

### Criterios de Aceptación

```
SETUP:
  [ ] Tenant A creado: free plan, max_scans=100/día
  [ ] Tenant B creado: pro plan, max_scans=10000/día
  [ ] 2 usuarios para cada tenant (reviewer + admin)
  
RLS ISOLATION:
  [ ] Escanear con Tenant A → findings en DB para Tenant A
  [ ] Escanear con Tenant B → findings en DB para Tenant B
  [ ] Query como admin-a → ve solo findings de Tenant A
  [ ] Query como admin-b → ve solo findings de Tenant B
  
QUOTA ENFORCEMENT:
  [ ] Tenant A hace 100 scans → 101º retorna 429
  [ ] Tenant B hace 100 scans → 101º retorna 202 (ok, quota es 10000)
  
AUDIT TRAIL:
  [ ] Todos los logs incluyen tenant_id
  [ ] Tenant A logs: tenant_id = uuid-aaaa
  [ ] Tenant B logs: tenant_id = uuid-bbbb
```

### Ejecución

```bash
# 1. Crear datos de prueba
python scripts/test-setup-phase2.py
# Output: /tmp/FASE2-tenants-created.json

# 2. Ejecutar tests de multi-tenancy
pytest tests/integration/test_multitenancy_rls.py -v
pytest tests/integration/test_multitenancy_quotas.py -v
pytest tests/integration/test_multitenancy_audit.py -v
# Todos deben pasar

# 3. Validar RLS escape detection
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT tenant_id FROM operations LIMIT 5;"
# Debe retornar: ERROR: policy... (RLS bloqueó)

# 4. Generar reporte
python scripts/generate-phase2-report.py > /tmp/FASE2-REPORT.md
```

### Artefactos Generados

- `/tmp/FASE2-tenants-created.json` — IDs de tenants creados
- `/tmp/FASE2-test-results.log` — Test output
- `/tmp/FASE2-REPORT.md` — Full isolation report

### Gate de Salida
- ✅ 2 tenants creados y configurados
- ✅ RLS tests pasan 100%
- ✅ Quota enforcement validado
- ✅ Audit trail segregado

**Si PASA FASE 2**: 
- ✅ Apto para abrir a **primeros clientes (2-3 empresas pilotos)**
- Proceder a FASE 3

**Si FALLA FASE 2**: 
- Diagnosticar qué componente falló (RLS, quotas, audit)
- Hacer fix, re-run tests

---

## FASE 3: Chain of Custody (Criptografía)

**Duración Estimada**: 4-5 horas  
**Responsable**: Security Team  
**Artefactos**: Chain integrity report, signatures validation, TSA tokens

### Objetivos
- ✅ Validar chain_hash computation
- ✅ Validar digital signatures (ECDSA-P256)
- ✅ Validar TSA RFC 3161 timestamps
- ✅ Validar WORM retention locks
- ✅ Validar cascade deletes

### Criterios de Aceptación

```
CHAIN HASH:
  [ ] 10 scans ejecutados en BD
  [ ] GET /v1/audit/chain/verify retorna valid=true
  [ ] Cambiar 1 operación en BD → verify retorna valid=false, gaps=1
  
DIGITAL SIGNATURES:
  [ ] Scan genera signature ECDSA-P256
  [ ] Transit verify_signature(artifact, signature) = true
  [ ] Modificar artifact → verify_signature = false
  
TSA TIMESTAMPS:
  [ ] Scan incluye tsa_token en audit trail
  [ ] Decodificar token → timestamp ±5 min de ahora
  [ ] Validar con openssl ts -verify → OK
  
WORM RETENTION:
  [ ] Artifact stored con retention=7 años
  [ ] Intentar delete antes de expiración → 403 AccessDenied
  [ ] MinIO Object Lock GOVERNANCE verificable
  
CASCADE DELETES:
  [ ] 1 op + 5 findings + 10 redactions + 3 artifacts
  [ ] GDPR purge → operación + findings + artifacts todos borrados
  [ ] Integridad relacional mantenida
```

### Ejecución

```bash
# 1. Crear operaciones para validar chain
python scripts/test-phase3-chain-custody.py --num-scans=10
# Output: /tmp/FASE3-scans-created.json

# 2. Validar chain integrity
pytest tests/integration/test_chain_custody.py -v
# Tests: chain_hash, signatures, TSA, WORM, cascade

# 3. Validar TSA real
curl -X POST https://freetsa.org/tsr \
  -H "Content-Type: application/octet-stream" \
  -d @/tmp/FASE3-hash-to-timestamp.der > /tmp/FASE3-tsa-token.tsr
openssl ts -verify -in /tmp/FASE3-tsa-token.tsr

# 4. Validar WORM enforcement
# (Manual test con MinIO CLI)

# 5. Generar reporte de seguridad
python scripts/generate-phase3-security-report.py > /tmp/FASE3-SECURITY-REPORT.md
```

### Artefactos Generados

- `/tmp/FASE3-scans-created.json` — Operations para validación
- `/tmp/FASE3-chain-verification.json` — Chain integrity results
- `/tmp/FASE3-tsa-token.tsr` — Real TSA token
- `/tmp/FASE3-SECURITY-REPORT.md` — Full security validation

### Gate de Salida
- ✅ Chain integrity validado (tamper detection funciona)
- ✅ Digital signatures verificables
- ✅ TSA timestamps válidos
- ✅ WORM locks enforcing retention
- ✅ Cascade deletes mantienen integridad

**Si PASA FASE 3**: 
- ✅ Apto para abrir a **clientes con requisitos de compliance legal**
- Proceder a FASE 4

**Si FALLA FASE 3**: 
- Revisar qué falló (chain, signatures, TSA, WORM)
- Hacer fix, re-run security tests

---

## FASE 4: Compliance & GDPR

**Duración Estimada**: 4-5 horas  
**Responsable**: Compliance + Security  
**Artefactos**: Compliance reports, GDPR purge certificates, SIEM logs

### Objetivos
- ✅ Validar compliance reports (SOC2, ISO27001, GDPR)
- ✅ Validar GDPR purge con certificados
- ✅ Validar SIEM integration (CEF/LEEF/JSON)
- ✅ Validar pen-test gate (ZAP)
- ✅ Validar SBOM supply chain

### Criterios de Aceptación

```
COMPLIANCE REPORTS:
  [ ] GET /v1/admin/compliance/report?framework=soc2 → 200 OK
  [ ] GET /v1/admin/compliance/report?framework=iso27001 → 200 OK
  [ ] GET /v1/admin/compliance/report?framework=gdpr → 200 OK
  [ ] Reportes incluyen controles mapeados a evidencia real
  
GDPR PURGE:
  [ ] Crear 100 operations aged >30 days
  [ ] POST /v1/admin/tenants/{id}/retention/purge
  [ ] Retorna deletion_certificate_id
  [ ] Certificate contenido: deleted_count=100, signature válida
  [ ] Operaciones y artifacts completamente eliminados de BD
  
SIEM INTEGRATION:
  [ ] Configurar webhook en tenant
  [ ] Hacer scan → genera SIEM event en CEF format
  [ ] Event llega a webhook endpoint (o syslog)
  [ ] Event contiene: trace_id, actor_id, entity_type, severity
  
PEN-TEST GATE:
  [ ] Ejecutar ZAP baseline scan contra API
  [ ] Verificar 0 high/critical vulnerabilities
  
SBOM SUPPLY CHAIN:
  [ ] Git tag v1.0.0-test → GitHub Actions genera SBOM
  [ ] Cosign firma SBOM
  [ ] cosign verify-blob valida firma
```

### Ejecución

```bash
# 1. Test compliance reports
curl "http://localhost:8000/v1/admin/compliance/report?framework=soc2" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq . > /tmp/FASE4-compliance-soc2.json

# 2. Test GDPR purge
python scripts/test-phase4-gdpr-purge.py
# Output: /tmp/FASE4-gdpr-purge-results.json, /tmp/FASE4-deletion-certificate.json

# 3. Test SIEM
python scripts/test-phase4-siem-integration.py
# Output: /tmp/FASE4-siem-events.log

# 4. ZAP scan
docker run --rm -v /tmp/zapreports:/zap/reports \
  owasp/zap2docker-stable zap-baseline.py \
  -t http://nginx:8088 -r /zap/reports/zap-report.md

# 5. Generate report
python scripts/generate-phase4-compliance-report.py > /tmp/FASE4-COMPLIANCE-REPORT.md
```

### Artefactos Generados

- `/tmp/FASE4-compliance-soc2.json` — SOC2 compliance report
- `/tmp/FASE4-compliance-iso27001.json` — ISO27001 report
- `/tmp/FASE4-gdpr-purge-results.json` — GDPR purge validation
- `/tmp/FASE4-deletion-certificate.json` — Signed deletion certificate
- `/tmp/FASE4-siem-events.log` — SIEM delivery logs
- `/tmp/FASE4-zap-report.md` — Security scan report
- `/tmp/FASE4-COMPLIANCE-REPORT.md` — Full compliance summary

### Gate de Salida
- ✅ Compliance reports generan correctamente
- ✅ GDPR purge funciona con certificados verificables
- ✅ SIEM delivery ≥99% success rate
- ✅ ZAP scan: 0 high/critical vulnerabilities
- ✅ SBOM signed y verificable

**Si PASA FASE 4**: 
- ✅ Apto para abrir a **clientes sujetos a regulaciones (GDPR, SOC2, HIPAA)**
- Proceder a FASE 5

**Si FALLA FASE 4**: 
- Revisar qué falló (compliance, GDPR, SIEM, ZAP)
- Hacer fix, re-run compliance tests

---

## FASE 5: Security & Admin Module

**Duración Estimada**: 4-5 horas  
**Responsable**: Security + Product  
**Artefactos**: OIDC flow logs, RBAC matrix validation, admin module tests

### Objetivos
- ✅ Validar OIDC/MFA flow end-to-end
- ✅ Validar RBAC 4 roles × 20+ endpoints
- ✅ Validar SoD (self-approval blocking)
- ✅ Validar admin module CRUD
- ✅ Validar cross-tenant isolation (admin scope)

### Criterios de Aceptación

```
OIDC/MFA:
  [ ] Login en Keycloak requiere MFA (OTP)
  [ ] JWT obtenido incluye claims correctos
  [ ] JWT expiración respetada
  [ ] Token refresh funciona
  
RBAC ENFORCEMENT:
  [ ] viewer: GET /operations, prohibido POST /scan
  [ ] reviewer: POST /scan + PUT /review, prohibido PATCH /waivers
  [ ] policy_editor: PATCH /waivers, prohibido PATCH /tenants
  [ ] admin: todos los endpoints permitidos
  [ ] Matriz 80+ combinaciones testada
  
SoD ENFORCEMENT:
  [ ] User A scans documento
  [ ] User A intenta aprobar su propio scan → 403 Forbidden
  [ ] User B aprueba scan de A → 200 OK
  
ADMIN MODULE:
  [ ] admin puede crear tenant
  [ ] admin puede configurar policy overrides
  [ ] admin puede configurar SIEM webhook
  [ ] admin puede crear/revocar waivers
  [ ] admin puede ejecutar GDPR purge
  
CROSS-TENANT ISOLATION:
  [ ] admin-a no puede ver datos de tenant B
  [ ] admin-a listar operaciones → solo tenant A
  [ ] admin-a GET /audit/op-from-tenant-B → 403 Forbidden
```

### Ejecución

```bash
# 1. OIDC/MFA flow
python scripts/test-phase5-oidc-mfa.py
# Output: /tmp/FASE5-oidc-mfa-results.json

# 2. RBAC matrix testing
pytest tests/integration/test_rbac_matrix.py -v
# 80+ test cases, todas deben pasar

# 3. SoD testing
pytest tests/integration/test_sod_enforcement.py -v
# Self-approval debe estar bloqueado

# 4. Admin module E2E
pytest tests/integration/test_admin_module_e2e.py -v
# CRUD operations deben funcionar

# 5. Generate report
python scripts/generate-phase5-security-report.py > /tmp/FASE5-SECURITY-REPORT.md
```

### Artefactos Generados

- `/tmp/FASE5-oidc-mfa-results.json` — OIDC/MFA validation
- `/tmp/FASE5-rbac-matrix-results.json` — RBAC enforcement matrix
- `/tmp/FASE5-sod-test-results.log` — SoD enforcement tests
- `/tmp/FASE5-admin-module-tests.log` — Admin module E2E tests
- `/tmp/FASE5-SECURITY-REPORT.md` — Full security assessment

### Gate de Salida
- ✅ OIDC/MFA flow funciona end-to-end
- ✅ RBAC 80+ combinaciones validadas
- ✅ SoD enforcement bloqueando auto-aprobaciones
- ✅ Admin module CRUD funcional
- ✅ Cross-tenant isolation verificado

**Si PASA FASE 5**: 
- ✅ Apto para desplegar a **clientes empresariales con múltiples usuarios/roles**
- Proceder a FASE 6

**Si FALLA FASE 5**: 
- Revisar qué falló (OIDC, RBAC, SoD, admin)
- Hacer fix, re-run security tests

---

## FASE 6: Observability & Load Testing

**Duración Estimada**: 3-4 horas  
**Responsable**: SRE + Performance  
**Artefactos**: Load test report, trace correlation logs, metrics dashboard

### Objetivos
- ✅ Validar trace correlation end-to-end
- ✅ Validar Prometheus metrics accuracy
- ✅ Validar structured logging
- ✅ Validar load SLAs (p50<2s, p95<5s, p99<10s)

### Criterios de Aceptación

```
TRACE CORRELATION:
  [ ] Hacer scan → genera trace_id
  [ ] trace_id aparece en API logs
  [ ] trace_id aparece en worker logs
  [ ] trace_id aparece en audit DB
  [ ] trace_id correlaciona todos los eventos
  
PROMETHEUS METRICS:
  [ ] safecontext_scan_duration_seconds_count = 50 (50 scans)
  [ ] safecontext_findings_total incrementa por cada finding
  [ ] safecontext_detector_recall visible para cada detector
  
STRUCTURED LOGGING:
  [ ] API logs son JSON válido
  [ ] Cada línea incluye: timestamp, level, event, trace_id, actor_id
  [ ] pgAudit logs incluyen operaciones
  
LOAD SLA:
  [ ] 50 concurrent scans ejecutados
  [ ] p50 latency < 2000ms
  [ ] p95 latency < 5000ms
  [ ] p99 latency < 10000ms
  [ ] 0 errores 5xx durante load
```

### Ejecución

```bash
# 1. Trace correlation test
python scripts/test-phase6-trace-correlation.py
# Output: /tmp/FASE6-trace-correlation.json

# 2. Prometheus metrics validation
curl "http://localhost:9090/api/v1/query?query=safecontext_scan_duration_seconds_count" \
  > /tmp/FASE6-metrics.json

# 3. Structured log parsing
docker compose logs api 2>&1 | grep '"event"' | head -10 > /tmp/FASE6-sample-logs.json

# 4. Load testing (50 concurrent scans)
python scripts/load-test-phase6.py \
  --concurrent=50 \
  --duration=300 \
  --output=/tmp/FASE6-load-results.json

# 5. Generate report
python scripts/generate-phase6-performance-report.py > /tmp/FASE6-PERFORMANCE-REPORT.md
```

### Artefactos Generados

- `/tmp/FASE6-trace-correlation.json` — Trace validation results
- `/tmp/FASE6-metrics.json` — Prometheus metrics snapshot
- `/tmp/FASE6-sample-logs.json` — Structured log samples
- `/tmp/FASE6-load-results.json` — Load test metrics (p50, p95, p99)
- `/tmp/FASE6-PERFORMANCE-REPORT.md` — Full performance assessment

### Gate de Salida
- ✅ Trace correlation funciona end-to-end
- ✅ Prometheus metrics preciso
- ✅ Structured logging validado
- ✅ Load SLAs cumplidos (p95<5s, p99<10s)
- ✅ 0 errores bajo carga

**Si PASA FASE 6**: 
- ✅ **LISTO PARA DESPLIEGUE A PRODUCCIÓN GENERAL**
- Todos los clientes pueden usar SafeContext

**Si FALLA FASE 6**: 
- Revisar qué falló (traces, metrics, load)
- Hacer fix/optimization, re-run load tests

---

## MATRIZ DE APERTURA A CLIENTES

| Fase | Gate Completado | Clientes Permitidos | Casos de Uso |
|------|---|---|---|
| **0** | Health checks | QA interno | Validación técnica |
| **1** | Tests existentes | Evaluadores técnicos | PoC, evaluación |
| **2** | Multi-tenancy | 2-3 pilotos | Primeros clientes reales |
| **3** | Chain of custody | Compliance-driven | Requisitos legales/criptografía |
| **4** | GDPR/Compliance | Regulados | GDPR, SOC2, HIPAA |
| **5** | Security/Admin | Empresariales | Multi-usuario, multi-tenant |
| **6** | Performance | General | Producción general (unlimited) |

---

## CHECKLIST POR FASE

### Para completar una fase:

```
[ ] Ejecutar todos los tests de la fase
[ ] Generar reporte (markdown + JSON)
[ ] Validar criterios de aceptación
[ ] Revisar artefactos generados
[ ] Documentar cualquier issue encontrado
[ ] Gate de salida PASA o FALLA
[ ] Si PASA: autorizar apertura a próxima categoría de clientes
[ ] Si FALLA: crear issue, hacer fix, re-run
```

---

## PRÓXIMOS PASOS

1. **Hoy**: Ejecutar FASE 0 (health checks)
2. **Mañana**: Ejecutar FASE 1 (existing tests)
3. **Día 3**: Ejecutar FASE 2 (multi-tenancy)
4. **Día 4**: Ejecutar FASE 3 (chain of custody)
5. **Día 5**: Ejecutar FASE 4 (compliance)
6. **Día 6**: Ejecutar FASE 5 (security/admin)
7. **Día 7**: Ejecutar FASE 6 (observability/load)

---

**Documento versión 1.0**  
**Creado**: 2026-05-28  
**Autor**: Claude (QA Strategy)

