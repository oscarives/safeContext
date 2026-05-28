# SafeContext — Manual de Operacion

**Versión**: 2.0.0 | **Fecha**: 2026-05-25 | **Audiencia**: SRE, DevOps, Operadores
**Documentos relacionados**: [Manual 07 — Administración](./07_ADMIN_CONFIGURACION.md), [Manual 09 — Seguridad](./09_SEGURIDAD_Y_COMPLIANCE.md)

---

## Tabla de Contenidos

1. [Requisitos de sistema](#1-requisitos-de-sistema)
2. [Instalacion y primer arranque](#2-instalacion-y-primer-arranque)
3. [Gestion del stack](#3-gestion-del-stack)
4. [Monitoreo](#4-monitoreo)
5. [Runbooks operacionales](#5-runbooks-operacionales)
6. [Backup y Disaster Recovery](#6-backup-y-disaster-recovery)
7. [Seguridad operacional](#7-seguridad-operacional)
8. [Escalado](#8-escalado)
9. [Logs estructurados](#9-logs-estructurados)
10. [Checklist de health pre-produccion](#10-checklist-de-health-pre-produccion)

---

## 1. Requisitos de sistema

### Hardware minimo

| Recurso | Minimo | Recomendado |
|---|---|---|
| RAM | 4 GB | 8 GB |
| CPU | 2 vCPU | 4 vCPU |
| Disco libre | 20 GB | 50 GB |
| SO | Linux 64-bit, macOS 13+, Windows 11 | Linux 64-bit (produccion) |

### Software requerido

| Componente | Version minima | Notas |
|---|---|---|
| Docker Engine / Desktop | 24.0+ | Con BuildKit habilitado |
| Docker Compose | V2 plugin (compose v2.20+) | `docker compose` (sin guion) |
| `curl` | Cualquier version reciente | Para verificacion de healthchecks |
| `jq` | 1.6+ | Para parsear logs JSON |
| `openssl` | 1.1.1+ | Para generacion de certificados TLS |

### Puertos requeridos

| Puerto | Servicio | Protocolo |
|---|---|---|
| 8000 | API (FastAPI) | HTTP/HTTPS |
| 8088 | UI (Next.js) | HTTP/HTTPS |
| 3001 | Grafana | HTTP |
| 9090 | Prometheus | HTTP |
| 9001 | MinIO Console | HTTP |
| 8080 | Keycloak SSO | HTTP/HTTPS |
| 8200 | Vault KMS | HTTP/HTTPS |
| 5432 | PostgreSQL | TCP |
| 6379 | Redis | TCP |

> **Nota de seguridad**: En produccion, los puertos 5432 y 6379 NO deben exponerse fuera de la red Docker. Solo accesibles internamente entre contenedores.

---

## 2. Instalacion y primer arranque

### Paso 1: Clonar el repositorio

```bash
git clone https://github.com/oscarives/safeContext.git
cd safeContext
```

### Paso 2: Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con los valores correspondientes al entorno. Las variables criticas se detallan en la seccion [3.3](#33-variables-de-entorno-criticas). Como minimo, cambiar:

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `VAULT_DEV_ROOT_TOKEN_ID`
- `KEYCLOAK_ADMIN_PASSWORD`
- `SECRET_KEY` (para firma HMAC)

### Paso 3: Generar certificados TLS

```bash
sh infra/compose/generate-certs.sh
```

Esto genera certificados autofirmados en `infra/certs/`. Para produccion, reemplazar con certificados firmados por una CA valida.

### Paso 4: Construir las imagenes

```bash
docker compose build
```

> **Aviso**: La primera construccion puede tardar entre 10 y 20 minutos porque descarga los modelos de spaCy (aproximadamente 800 MB). Las construcciones subsecuentes usan la capa cacheada.

### Paso 5: Levantar el stack

```bash
# Stack minimo (sin auth, sin vault) — ideal para desarrollo rapido
docker compose up -d

# Stack con Keycloak + OpenBao (Vault) — necesario para flujos con SSO/MFA
docker compose --profile auth up -d

# Stack completo (incluye auth)
docker compose --profile full up -d
```

> **Nota**: Keycloak y OpenBao (Vault) estan en profiles opcionales. El API arranca sin ellos (JWT validation falla gracefully con warning). Activar `--profile auth` cuando se necesite SSO/MFA o rotacion de claves KMS.

El orden de arranque esta controlado por `depends_on` en `docker-compose.yml`. Esperar aproximadamente 60-90 segundos para que todos los servicios pasen sus healthchecks.

### Paso 6: Ejecutar migraciones de base de datos

```bash
docker compose exec api alembic upgrade head
```

Este comando es idempotente. Ejecutarlo tambien tras cada actualizacion que incluya cambios de esquema.

### Paso 7: Verificar que el stack esta saludable

```bash
curl http://localhost:8000/health
```

Respuesta esperada:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "minio": "healthy",
    "broker": "healthy"
  }
}
```

Si algun componente reporta `"unhealthy"`, consultar la seccion [5. Runbooks operacionales](#5-runbooks-operacionales).

---

## 3. Gestion del stack

### 3.1 Comandos esenciales

| Comando | Descripcion | Cuando usarlo |
|---|---|---|
| `docker compose up -d` | Levanta stack minimo (sin auth/vault) | Desarrollo rapido sin SSO |
| `docker compose --profile auth up -d` | Stack con Keycloak + OpenBao | Desarrollo con SSO/MFA |
| `docker compose --profile full up -d` | Stack completo (incluye auth) | Entorno que replica produccion |
| `docker compose down` | Para y elimina contenedores (conserva volumenes) | Apagado controlado |
| `docker compose down -v` | Para, elimina contenedores Y volumenes | Solo en reset completo de datos |
| `docker compose restart [servicio]` | Reinicia un servicio especifico | Tras cambio de configuracion |
| `docker compose logs [servicio]` | Muestra logs de un servicio | Diagnostico de errores |
| `docker compose logs -f [servicio]` | Logs en tiempo real (follow) | Monitoreo durante incidente |
| `docker compose ps` | Estado de todos los contenedores | Verificacion rapida de health |
| `docker compose exec api alembic upgrade head` | Aplica migraciones de BD pendientes | Tras deploy con cambios de esquema |
| `docker compose exec api python -m pytest tests/` | Ejecuta la suite de tests | Verificacion post-deploy |
| `docker compose pull` | Descarga imagenes actualizadas | Antes de un upgrade |
| `docker compose up -d --scale worker=3` | Escala los workers a 3 replicas | Ante picos de carga |
| `docker compose build --no-cache api` | Reconstruye la imagen de API sin cache | Tras cambios en Dockerfile |

### 3.2 Servicios y healthchecks

| Servicio | Puerto | Endpoint de Healthcheck | Estado esperado | Tiempo de arranque |
|---|---|---|---|---|
| `api` | 8000 | `GET /health` | `{"status":"healthy"}` | 15-30 s |
| `ui` | 8088 | `GET /` (nginx status 200) | HTTP 200 | 10-15 s |
| `postgres` | 5432 | `pg_isready -U safecontext` | `accepting connections` | 5-10 s |
| `redis` | 6379 | `redis-cli ping` | `PONG` | 3-5 s |
| `minio` | 9000/9001 | `GET /minio/health/live` | HTTP 200 | 10-15 s |
| `opa` | 8181 | `GET /health` | `{}` HTTP 200 | 5-10 s |
| `worker` | — | Exit code 0 en healthcheck interno | Running | 20-30 s |
| `keycloak` | 8080 | `GET /health/ready` | `{"status":"UP"}` | 45-60 s |
| `vault` | 8200 | `GET /v1/sys/health` | HTTP 200 | 5-10 s |
| `prometheus` | 9090 | `GET /-/healthy` | `Prometheus is Healthy.` | 5-10 s |
| `grafana` | 3001 | `GET /api/health` | `{"database":"ok"}` | 10-15 s |
| `presidio-analyzer` | 5001 | `GET /health` | HTTP 200 | 30-45 s |

> **Total tiempo de arranque completo**: Aproximadamente 90-120 segundos hasta que todos los servicios estan healthy.

### 3.3 Variables de entorno criticas

| Variable | Descripcion | Valor de ejemplo | Impacto si falta |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Contrasena de PostgreSQL | `s3cr3tP@ss!` | API no puede conectar a BD — stack inoperativo |
| `REDIS_PASSWORD` | Contrasena de Redis | `r3d1sP@ss!` | Workers no pueden encolar tareas — sin procesamiento async |
| `MINIO_ROOT_USER` | Usuario administrador de MinIO | `safecontext` | No se pueden crear buckets ni subir artefactos |
| `MINIO_ROOT_PASSWORD` | Contrasena de MinIO | `m1n10P@ss!` | No se pueden crear buckets ni subir artefactos |
| `VAULT_DEV_ROOT_TOKEN_ID` | Token de acceso a Vault (dev) | `root-token-dev` | KMS inoperativo — cifrado/descifrado falla |
| `KEYCLOAK_ADMIN_PASSWORD` | Contrasena admin de Keycloak | `kc@dm1nP@ss!` | No se pueden crear usuarios ni configurar SSO |
| `SECRET_KEY` | Clave para firma HMAC de audit trail | 64 chars aleatorios | Firmas invalidas — evidencia de auditoria no verificable |
| `OPA_BUNDLE_URL` | URL del bundle de politicas OPA | `http://opa:8181` | Sin politica activa — todos los scans fallan |
| `PRESIDIO_ANALYZER_URL` | URL del servicio Presidio | `http://presidio-analyzer:5001` | Sin deteccion de PII — stack inoperativo |
| `DATABASE_URL` | URL completa de conexion a PostgreSQL | `postgresql://user:pass@postgres:5432/safecontext` | API no arranca |
| `CELERY_BROKER_URL` | URL de Redis para Dramatiq/Celery | `redis://:pass@redis:6379/0` | Workers no procesan mensajes |
| `MINIO_ENDPOINT` | Endpoint de MinIO | `minio:9000` | No se guardan artefactos |

---

## 4. Monitoreo

### 4.1 Prometheus — metricas clave

**URL**: http://localhost:9090

#### Queries PromQL utiles

**Disponibilidad del servicio de scan**
```promql
up{job="safecontext-api"}
```
Valor esperado: `1`. Si es `0`, la API esta caida.

**Latencia p95 de scans (ultimos 5 minutos)**
```promql
histogram_quantile(0.95, rate(safecontext_scan_duration_seconds_bucket[5m]))
```
Objetivo: `< 5.0` segundos para documentos < 1 MB.

**Recall del detector por clase de entidad**
```promql
safecontext_detector_recall{entity_class=~"PERSON|EMAIL|PHONE_NUMBER|IBAN"}
```
Objetivo: `>= 0.90` por clase. Alerta si baja de `0.85`.

**Profundidad de la Dead Letter Queue (DLQ)**
```promql
safecontext_dlq_depth
```
Objetivo: `0`. Alerta si supera `10` mensajes.

**Error rate de la API (ultimos 5 minutos)**
```promql
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])
```
Objetivo: `< 0.001` (menos del 0.1%). SLO: error budget mensual `< 0.1%`.

**Workers activos**
```promql
safecontext_workers_active
```
Objetivo: `>= 1`. Si es `0`, no hay procesamiento async.

**Throughput de scans por minuto**
```promql
rate(safecontext_scans_total[1m]) * 60
```
Baseline esperado en produccion: definir segun carga del cliente.

### 4.2 Grafana — dashboards

**URL**: http://localhost:3001 | **Credenciales por defecto**: `admin` / `admin`

> Cambiar la contrasena de Grafana en el primer acceso.

#### Dashboard: SafeContext Overview

Panel principal de operaciones. Incluye:

- **Latencia de scan**: grafico de serie temporal con p50, p95, p99
- **Throughput**: scans por minuto, desglosado por resultado (approved/rejected/pending_review)
- **Error rate**: porcentaje de errores 5xx en ventana deslizante de 5 minutos
- **Recall por clase**: gauge por entidad (PERSON, EMAIL, IBAN, PHONE, etc.)
- **Workers activos**: numero de workers Dramatiq en estado running
- **DLQ depth**: contador con alerta visual si > 0

#### Dashboard: Error Budget

Panel de SLO. Incluye:

- **SLO objetivo**: 99.9% de disponibilidad
- **Error budget mensual**: minutos de downtime disponibles (43.8 min/mes)
- **Burn rate**: velocidad a la que se consume el budget — alerta si burn rate > 1x en 1 hora
- **Budget restante**: porcentaje consumido en el mes actual
- **Historial de incidentes**: ventana de 30 dias

### 4.3 Alertas activas

| Alerta | Condicion (PromQL) | Severidad | Accion recomendada |
|---|---|---|---|
| `DLQDepthHigh` | `safecontext_dlq_depth > 10` durante 5 min | `warning` | Consultar runbook [5.2](#52-dlq-tiene-mensajes) |
| `DLQDepthCritical` | `safecontext_dlq_depth > 50` durante 2 min | `critical` | Escalar inmediatamente, consultar runbook [5.2](#52-dlq-tiene-mensajes) |
| `SLOErrorBudgetLow` | Error budget < 20% restante en el mes | `warning` | Congelar deploys, revisar causas de errores 5xx |
| `SLOErrorBudgetBurning` | Burn rate > 5x durante 30 min | `critical` | Activar protocolo de incidente, rollback si aplica |
| `DetectorRecallLow` | `safecontext_detector_recall < 0.85` | `warning` | Consultar runbook `docs/runbooks/model-update.md` |
| `WorkerHighLatency` | p95 latencia > 10 s durante 10 min | `warning` | Escalar workers: `docker compose up -d --scale worker=3` |
| `WorkerDown` | `safecontext_workers_active == 0` durante 2 min | `critical` | Consultar runbook [5.1](#51-worker-no-procesa-mensajes) |
| `APIDown` | `up{job="safecontext-api"} == 0` durante 1 min | `critical` | Consultar logs: `docker compose logs api` |
| `DatabaseConnectionFailed` | API reporta `database: unhealthy` | `critical` | Consultar runbook [5.3](#53-base-de-datos-no-responde) |

---

## 5. Runbooks operacionales

### 5.1 Worker no procesa mensajes

**Sintomas**:
- Dashboard muestra `workers_active = 0`
- Operaciones quedan en estado `processing` indefinidamente
- Alerta `WorkerDown` disparada
- Logs de API muestran `No workers available`

**Diagnostico**:

```bash
# 1. Verificar estado del contenedor worker
docker compose ps worker

# 2. Ver los ultimos logs del worker
docker compose logs --tail=100 worker

# 3. Verificar conexion con Redis (broker de mensajes)
docker compose exec worker redis-cli -h redis -p 6379 -a $REDIS_PASSWORD ping

# 4. Verificar que Redis tiene mensajes encolados
docker compose exec redis redis-cli -a $REDIS_PASSWORD llen safecontext:queue:default
```

**Pasos de recuperacion**:

```bash
# Paso 1: Reiniciar el worker
docker compose restart worker

# Paso 2: Verificar que arranca correctamente
docker compose logs -f worker
# Esperar a ver: "Worker started. Listening for messages..."

# Paso 3: Si no arranca, verificar conexion con Redis
docker compose restart redis
docker compose restart worker

# Paso 4: Si el problema persiste, verificar memoria disponible
docker stats worker

# Paso 5: Escalar workers si hay backlog acumulado
docker compose up -d --scale worker=3
```

**Escalacion**: Si tras los pasos anteriores el worker no arranca en 5 minutos, abrir incidente P1 y revisar logs completos buscando OOM (Out of Memory) o errores de importacion de modelos ML.

---

### 5.2 DLQ tiene mensajes

La Dead Letter Queue (DLQ) contiene mensajes que fallaron despues de todos los reintentos configurados. Cada mensaje en la DLQ representa una operacion que NO fue procesada.

**Referencia completa**: `docs/runbooks/dlq-recovery.md`

**Resumen del proceso**:

```bash
# 1. Ver cuantos mensajes hay en DLQ
docker compose exec redis redis-cli -a $REDIS_PASSWORD llen safecontext:queue:dead

# 2. Inspeccionar el primer mensaje para entender la causa
docker compose exec redis redis-cli -a $REDIS_PASSWORD lindex safecontext:queue:dead 0

# 3. Si la causa fue un error transitorio (red, OOM temporal):
#    Mover mensajes de DLQ de vuelta a la cola principal
docker compose exec api python -m scripts.dlq_replay --all

# 4. Si la causa fue un error de datos (documento corrupto):
#    Descartar los mensajes invalidos con justificacion documentada
docker compose exec api python -m scripts.dlq_discard --reason "documento corrupto - ver trace_id XXXX"

# 5. Verificar que la DLQ quedo vacia
docker compose exec redis redis-cli -a $REDIS_PASSWORD llen safecontext:queue:dead
```

**Politica de retencion de DLQ**: Los mensajes en DLQ se retienen 7 dias antes de expirar automaticamente. Siempre documentar la accion tomada (replay vs discard) en el sistema de tickets.

---

### 5.3 Base de datos no responde

**Sintomas**:
- `GET /health` devuelve `"database": "unhealthy"`
- Logs de API muestran `psycopg2.OperationalError: could not connect to server`
- Alerta `DatabaseConnectionFailed` disparada

**Diagnostico**:

```bash
# 1. Verificar estado del contenedor
docker compose ps postgres

# 2. Ver logs de PostgreSQL
docker compose logs --tail=50 postgres

# 3. Intentar conexion directa
docker compose exec postgres pg_isready -U safecontext -d safecontext
```

**Pasos de recuperacion**:

```bash
# Paso 1: Reinicio simple (sin perdida de datos)
docker compose restart postgres

# Paso 2: Esperar que el healthcheck pase
docker compose ps postgres
# Esperar estado: "healthy"

# Paso 3: Reiniciar la API para que restablezca el pool de conexiones
docker compose restart api

# Paso 4: Verificar
curl http://localhost:8000/health
```

> **IMPORTANTE**: NUNCA ejecutar `docker compose down -v` para resolver un problema de base de datos. Esto destruye los volumenes y todos los datos. Si el problema requiere un rebuild completo, hacer backup primero (seccion [6.1](#61-postgresql)).

---

### 5.4 MinIO no accesible

**Sintomas**:
- Uploads de artefactos fallan con `S3Error: connection refused`
- Dashboard muestra escaneos completados pero sin artefactos asociados
- `GET /health` devuelve `"minio": "unhealthy"`

**Diagnostico**:

```bash
# 1. Verificar estado del contenedor
docker compose ps minio

# 2. Ver logs de MinIO
docker compose logs --tail=50 minio

# 3. Verificar healthcheck
curl http://localhost:9000/minio/health/live
```

**Pasos de recuperacion**:

```bash
# Paso 1: Reiniciar MinIO
docker compose restart minio

# Paso 2: Esperar healthcheck
docker compose ps minio
# Estado esperado: healthy

# Paso 3: Verificar que los buckets existen
docker compose exec minio mc ls local/

# Paso 4: Si los buckets no existen, recrearlos
docker compose exec api python -m scripts.init_minio_buckets

# Paso 5: Reiniciar API
docker compose restart api
```

---

### 5.5 OPA no carga la politica

**Sintomas**:
- Respuesta de scan incluye `"policy_version": null` o el campo esta ausente
- Scans devuelven error `500: policy evaluation failed`
- `docker compose logs opa` muestra `bundle load failed` o `policy not found`

**Diagnostico**:

```bash
# 1. Verificar estado de OPA
curl http://localhost:8181/health

# 2. Verificar que la politica esta cargada
curl http://localhost:8181/v1/policies

# 3. Verificar que el bundle se descargo correctamente
docker compose logs opa | grep -i "bundle\|policy\|error"
```

**Pasos de recuperacion**:

```bash
# Paso 1: Verificar que el archivo de politica existe
ls -la policies/base/safecontext.rego

# Paso 2: Validar sintaxis de la politica
docker compose exec opa opa check policies/base/safecontext.rego

# Paso 3: Reiniciar OPA (recarga el bundle al arrancar)
docker compose restart opa

# Paso 4: Verificar que la politica se cargo
curl http://localhost:8181/v1/policies
# Debe devolver la politica "safecontext" con policy_version definido

# Paso 5: Verificar evaluacion de ejemplo
curl -X POST http://localhost:8181/v1/data/safecontext/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"findings": [], "actor": {"role": "api"}}}'
```

Si la politica sigue sin cargar tras el restart, revisar que el volumen `./policies` esta correctamente montado en el `docker-compose.yml` y que el archivo `safecontext.rego` no tiene errores de sintaxis.

---

## 6. Backup y Disaster Recovery

### 6.1 PostgreSQL

#### Backup automatico

El servicio `pg-backup` ejecuta un dump completo cada 24 horas. Los archivos se guardan en el volumen Docker `pg_backups`, montado en `/backups/postgres` dentro del contenedor.

Formato del archivo: `safecontext_backup_YYYYMMDD_HHMMSS.sql.gz`

```bash
# Verificar que los backups se estan generando
docker compose exec pg-backup ls -lh /backups/postgres/

# Backup manual (bajo demanda)
docker compose exec postgres pg_dump -U safecontext safecontext | gzip > /tmp/manual_backup_$(date +%Y%m%d).sql.gz
```

#### Restore desde backup

```bash
# 1. Identificar el backup a restaurar
docker compose exec pg-backup ls /backups/postgres/

# 2. Ejecutar restore (reemplazar TIMESTAMP con el valor real)
docker compose exec postgres /pg-restore.sh 20260518_120000

# 3. El script hace:
#    - Para la API y workers (para evitar escrituras durante restore)
#    - Drop y recreacion de la base de datos
#    - Restore desde el dump comprimido
#    - Reinicio de la API y workers

# 4. Verificar integridad post-restore
docker compose exec api python -m scripts.verify_db_integrity
```

**RTO objetivo**: Menos de 1 hora desde la decision de restore hasta stack operativo.

**RPO objetivo**: Menos de 5 minutos con WAL archiving activo. Configurar `archive_mode = on` en `postgresql.conf` para produccion.

### 6.2 MinIO

#### Mirror automatico

```bash
# Ejecutar mirror manual a bucket de backup
sh infra/compose/minio-backup.sh

# El script configura mc mirror de:
#   safecontext-artifacts → safecontext-artifacts-backup
#   safecontext-audit → safecontext-audit-backup
```

Para backup continuo, agregar el script al cron del host o habilitar replicacion bucket-to-bucket en produccion con MinIO SITE replication.

#### Objetos WORM (Write Once Read Many)

Los artefactos de auditoria en el bucket `safecontext-audit` estan configurados con Object Locking. Durante el periodo de retencion configurado (por defecto 90 dias):

- No pueden ser eliminados, ni por el usuario admin
- No pueden ser sobreescritos
- Solo pueden leerse

Esto garantiza la inmutabilidad de la evidencia de auditoria para cumplimiento normativo.

### 6.3 DR Drill trimestral

El drill de Disaster Recovery se ejecuta trimestralmente para verificar que los RTO/RPO son alcanzables en la practica.

**Referencia**: `docs/runbooks/dr-drill.md`

**Calendario**:

| Drill | Fecha objetivo | Responsable |
|---|---|---|
| Q3 2026 | Julio 2026 | SRE Lead |
| Q4 2026 | Octubre 2026 | SRE Lead |
| Q1 2027 | Enero 2027 | SRE Lead |

**Criterios de exito del drill**:
- RTO real <= 15 minutos
- RPO real <= 5 minutos (verificado por timestamp del ultimo registro)
- Todos los healthchecks en `healthy` al finalizar
- Verificacion de integridad de datos exitosa

---

## 7. Seguridad operacional

### 7.1 Rotacion de claves (KMS)

OpenBao 2.5.4 (fork MPL 2.0, Linux Foundation) gestiona el ciclo de vida de las claves criptograficas usadas para cifrar artefactos en MinIO y firmar el audit trail.

**URL OpenBao**: http://localhost:8200
**Token de acceso**: definido en `.env` como `VAULT_DEV_ROOT_TOKEN_ID`

> En produccion, usar OpenBao con autenticacion AppRole en lugar del token de dev.

**Referencia completa**: `docs/runbooks/key-rotation.md`

**Frecuencia recomendada de rotacion**: Cada 90 dias, o inmediatamente si hay sospecha de compromiso.

```bash
# Ver estado de las claves activas
curl -H "X-Vault-Token: $VAULT_DEV_ROOT_TOKEN_ID" \
  http://localhost:8200/v1/transit/keys/safecontext-doc-key

# La rotacion se documenta en el runbook key-rotation.md
# Incluye pasos para re-cifrar artefactos existentes con la nueva clave
```

### 7.2 Actualizacion de modelos ML

Los modelos de spaCy y Presidio se actualizan periodicamente para mejorar el recall de deteccion de PII.

**Referencia completa**: `docs/runbooks/model-update.md`

**Proceso sin downtime**: Los modelos se montan desde el volumen `models_local` (path en host: `./models/local`). El proceso consiste en:

1. Descargar el nuevo modelo en un directorio temporal
2. Verificar metricas de recall con el conjunto de test
3. Hacer swap atomico del directorio
4. El servicio `presidio-analyzer` detecta el cambio y recarga el modelo sin reinicio

### 7.3 Actualizar certificados TLS

Los certificados autofirmados expiran cada 365 dias. Para renovarlos:

```bash
# Paso 1: Regenerar certificados
sh infra/compose/generate-certs.sh

# Paso 2: Reiniciar nginx para que cargue los nuevos certificados
docker compose restart nginx

# Paso 3: Verificar fecha de expiracion del nuevo certificado
openssl x509 -in infra/certs/server.crt -noout -dates
```

Para produccion con certificados de una CA valida (Let's Encrypt, etc.), reemplazar los archivos en `infra/certs/` y seguir el mismo proceso de restart.

### 7.4 Seguridad en Kubernetes

Todos los deployments K8s incluyen las siguientes restricciones de seguridad:

```yaml
# Pod-level
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  fsGroup: 1001

# Container-level
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
  readOnlyRootFilesystem: true  # api + ui (worker excluido — necesita escribir modelos ML)
```

**Ingress rate limiting** (nginx ingress controller):
- 50 requests/segundo por IP de origen
- Burst x3 (150 requests en rafaga)
- Max 20 conexiones concurrentes por IP

**Grafana**: Expuesto a traves de un Ingress dedicado con basic auth (`grafana-basic-auth` secret). Requiere configurar el htpasswd secret antes del primer deploy:

```bash
htpasswd -c auth admin
kubectl create secret generic grafana-basic-auth --from-file=auth -n safecontext
```

---

## 8. Escalado

### 8.1 Docker Compose (single-node)

Para aumentar la capacidad de procesamiento en un solo servidor:

```bash
# Escalar workers de Dramatiq a 3 replicas
docker compose up -d --scale worker=3

# Verificar que las replicas estan activas
docker compose ps worker

# Monitorear la distribucion de carga
docker stats $(docker compose ps -q worker)
```

**Limites de escalado en single-node**: Con 8 GB RAM, se recomienda un maximo de 4 workers. Cada worker consume aproximadamente 800 MB de RAM por los modelos spaCy cargados en memoria.

**Escalar la API** (si el bottleneck es en el endpoint de ingesta):

```bash
docker compose up -d --scale api=2
```

Nota: Al escalar la API, asegurarse de que el load balancer (nginx) este configurado para distribuir entre las replicas. Ver `infra/compose/nginx.conf`.

### 8.2 Kubernetes (multi-node)

Para despliegues de alta disponibilidad o escalado horizontal multi-nodo:

**Manifiestos**: `infra/k8s/`

```bash
# Aplicar manifiestos base
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/

# Verificar que el HPA esta activo
kubectl get hpa -n safecontext
```

**HPA configurado para**:

| Deployment | Min replicas | Max replicas | Trigger |
|---|---|---|---|
| `api` | 2 | 10 | CPU > 70% durante 60s |
| `worker` | 2 | 20 | Cola Redis > 100 mensajes |

**Consideraciones para Kubernetes**:
- PostgreSQL debe desplegarse fuera del cluster (RDS, CloudSQL, etc.) para durabilidad
- MinIO puede reemplazarse por S3, GCS, o Azure Blob
- Secrets deben gestionarse con Kubernetes Secrets o Vault Agent Injector
- Los manifiestos en `infra/k8s/` asumen un ingress controller instalado (nginx-ingress o Traefik)

---

## 9. Logs estructurados

SafeContext usa logging JSON estructurado en todos sus componentes. Cada entrada incluye:

| Campo | Tipo | Descripcion |
|---|---|---|
| `timestamp` | ISO 8601 | Momento exacto del evento |
| `level` | string | `debug`, `info`, `warning`, `error`, `critical` |
| `service` | string | Nombre del servicio que genera el log |
| `trace_id` | UUID | Identificador unico de la operacion de scan |
| `actor_id` | string | Usuario o sistema que inicio la operacion |
| `operation_id` | UUID | ID interno de la operacion en PostgreSQL |
| `message` | string | Descripcion legible del evento |
| `duration_ms` | number | Duracion de la operacion (cuando aplica) |
| `error` | object | Detalles del error (solo en nivel `error`/`critical`) |

### Queries utiles con jq

```bash
# Ver solo errores de la API
docker compose logs api | jq 'select(.level == "error")'

# Seguir logs de una operacion especifica por trace_id
docker compose logs -f api | jq 'select(.trace_id == "550e8400-e29b-41d4-a716-446655440000")'

# Ver latencias de scan en tiempo real
docker compose logs -f worker | jq 'select(.message == "scan_completed") | {trace_id, duration_ms}'

# Contar errores por tipo en los ultimos N logs
docker compose logs api | jq -r '.error.type // empty' | sort | uniq -c | sort -rn

# Exportar logs de un rango horario para analisis offline
docker compose logs --since "2026-05-18T10:00:00" --until "2026-05-18T11:00:00" api > /tmp/incident_logs.jsonl
```

---

## 10. Checklist de health pre-produccion

Completar esta lista antes de cada despliegue a produccion. Marcar cada item como [x] cuando este verificado.

### Infraestructura

- [ ] Todos los contenedores reportan estado `healthy` en `docker compose ps`
- [ ] `curl http://localhost:8000/health` devuelve todos los componentes en `healthy`
- [ ] Las migraciones de base de datos estan al dia: `alembic current` muestra la revision mas reciente
- [ ] Los certificados TLS tienen mas de 30 dias de vigencia restante

### Seguridad

- [ ] Las variables sensibles en `.env` estan configuradas con valores de produccion (NO los de ejemplo)
- [ ] El token de Vault de dev ha sido reemplazado por autenticacion AppRole
- [ ] La contrasena de Grafana no es `admin/admin`
- [ ] Los puertos 5432 y 6379 NO son accesibles desde fuera de la red Docker

### Monitoreo

- [ ] Prometheus scrape los 11 targets y todos estan `UP`
- [ ] El dashboard SafeContext Overview carga correctamente en Grafana
- [ ] Las alertas criticas estan configuradas con canal de notificacion valido (PagerDuty, Slack, email)
- [ ] La DLQ esta vacia: `safecontext_dlq_depth == 0`

### Backup y DR

- [ ] El servicio `pg-backup` tiene al menos un backup generado exitosamente
- [ ] Se ha verificado que el restore funciona (ejecutar `pg-restore.sh` en entorno de staging)
- [ ] El mirror de MinIO esta activo y sincronizado

### Funcional

- [ ] El scan end-to-end funciona: `POST /v1/mcp/tools/safecontext.scan` detecta PII en documento de prueba
- [ ] La politica OPA esta cargada: `GET /v1/mcp/tools/safecontext.policy.get` devuelve `policy_version` valido
- [ ] La revision humana funciona: crear un hallazgo de prueba y aprobarlo desde `/review`
- [ ] El audit trail es verificable: exportar un JSON y verificar la firma HMAC

### Tests

- [ ] Backend tests: `cd apps/api && python -m pytest tests/ -v` — 144+ passed
- [ ] Frontend unit tests: `cd apps/ui && npm test` — 112 passed (17 suites)
- [ ] OPA policy tests: `docker run --rm -v ./apps/policies:/policies openpolicyagent/opa:1.4.0 test /policies -v`
- [ ] E2E tests (requiere `--profile auth`): `cd apps/ui && npx playwright test`

### Operación SIEM

Si hay tenants con SIEM configurado:

- [ ] Verificar que los eventos llegan al destino: `POST /v1/admin/tenants/{id}/siem/test`
- [ ] Monitorear logs del API por errores `siem.webhook.failed` o `siem.syslog.failed`
- [ ] Verificar formatos de eventos en la plataforma SIEM receptora (CEF/LEEF/JSON)

### Operación GDPR / Retención

- [ ] Verificar configuración de `retention_days` por tenant (default 365)
- [ ] Verificar que los certificados de borrado se almacenan en WORM: `GET /v1/admin/tenants/{id}/certificates`
- [ ] Para purga manual: `POST /v1/admin/tenants/{id}/purge` (solo rol admin)
- [ ] Los certificados de borrado son inmutables por 7 años en MinIO

### Multi-tenancy

- [ ] Verificar que RLS está activo: `SHOW row_security` en PostgreSQL
- [ ] Verificar que cada tenant solo ve sus datos (probar con diferentes JWT)
- [ ] Verificar quotas por tenant: `max_scans_per_day`, `rate_limit_rpm`, `max_document_size`

---

*Manual de Operación SafeContext v2.0.0 — 2026-05-25*
*Mantener actualizado en cada release que cambie la configuración del stack.*
