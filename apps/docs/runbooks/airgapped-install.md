# Runbook: Instalación Air-Gapped

**Versión stack**: 2025.1 (Python 3.14, PostgreSQL 18.4, Node 24, Next.js 16.2)
**Prerrequisito**: bundle SafeContext descargado y transferido al host de destino

## Stack de componentes

| Servicio | Versión | Notas |
|---|---|---|
| PostgreSQL | 18.4-alpine | Mount: `/var/lib/postgresql` (no `/data`) |
| Redis | 7.4-alpine | Broker + cache |
| MinIO | RELEASE.2025-09-07 | S3 API, Community Edition |
| OPA | 1.4.0 | Policy engine (Rego v1) |
| Keycloak | 26.2.0 | SSO/MFA OIDC |
| OpenBao | 2.5.4 | KMS, fork MPL 2.0 de Vault |
| Prometheus | v3.11.3 | Métricas (scrape_protocols v3) |
| Grafana | 13.0.1 | Dashboards (usuario: admin) |
| API | Python 3.14 | FastAPI + PyJWT |
| Workers | Python 3.14 | Dramatiq + Presidio/spaCy |
| UI | Node 24, Next.js 16.2 | Frontend SSO |

## Proceso completo sin internet

### Paso 1: Transferir bundle al host de destino

```bash
# En máquina con internet:
scp dist/safecontext-bundle-1.0.0.tar.gz operator@airgapped-host:/opt/safecontext/
```

### Paso 2: Instalar desde bundle

```bash
cd /opt/safecontext
./infra/scripts/install-bundle.sh safecontext-bundle-1.0.0.tar.gz
```

### Paso 3: Configurar entorno

```bash
# El script ya creó .env desde .env.example
vim .env
# Campos mínimos requeridos:
#   POSTGRES_PASSWORD=<contraseña-fuerte>
#   API_SECRET_KEY=<clave-32-chars-min>
#   MCP_AUTH_TOKEN=<token-agentes-mcp>
#   KEYCLOAK_ADMIN_PASSWORD=<contraseña-admin>
#   MINIO_ACCESS_KEY=<usuario-minio>
#   MINIO_SECRET_KEY=<contraseña-minio>
#   API_REQUIRE_MFA=true  # producción: siempre true
#   NEXT_PUBLIC_KEYCLOAK_FORCE_MFA=true  # producción: siempre true
```

### Paso 4: Levantar stack

```bash
docker compose up -d
# Esperar ~2 minutos para que todos los servicios estén healthy
docker compose ps
```

### Paso 5: Aplicar migraciones de base de datos (OBLIGATORIO)

```bash
docker exec $(docker compose ps -q api) alembic upgrade head
# Esperado: Running upgrade 0001 -> 0002 -> 0003 -> 0004
```

### Paso 6: (Opcional) Inicializar OpenBao KMS para MinIO SSE

```bash
# Solo si se requiere cifrado en reposo con gestión de claves centralizada
docker exec $(docker compose ps -q vault) sh /init-openbao.sh
```

### Paso 7: Verificación de éxito

```bash
# API health check
curl http://localhost/health
# Esperado: {"status":"ok","postgres":"ok","redis":"ok","minio":"ok"}

# Stack completo
docker compose ps
# Todos los servicios: healthy

# Acceso a UI
# http://localhost:8088 → login SSO con Keycloak
# Al primer login: Keycloak solicitará configurar TOTP (MFA)

# Grafana (métricas)
# http://localhost:3001 → usuario: admin, contraseña: valor de API_SECRET_KEY
```

## Notas importantes de PostgreSQL 18

PostgreSQL 18 cambió el mount point del volumen de datos:
- **Antiguo (PG15)**: `/var/lib/postgresql/data`
- **Nuevo (PG18)**: `/var/lib/postgresql` (el engine crea subdirectorios por major version)

En docker-compose.yml ya está configurado correctamente. No editar este valor.

## Diferencias respecto a OpenBao vs HashiCorp Vault

OpenBao 2.5.4 es el reemplazo de HashiCorp Vault con licencia MPL 2.0 (Linux Foundation).
- CLI: `bao` en lugar de `vault` (el script init-openbao.sh usa ambos como fallback)
- API HTTP: 100% compatible — clientes apuntan a `VAULT_ADDR=http://vault:8200`
- Dev mode: activado por defecto en docker-compose (producción: usar agent HA)
