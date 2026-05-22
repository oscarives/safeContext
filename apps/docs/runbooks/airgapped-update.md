# Runbook: Actualización Air-Gapped

**Versión**: 1.0.0

## Upgrade N → N+1 sin internet

### Prerrequisito: backup del estado actual

```bash
mkdir -p backups
tar -czf backups/config-$(docker inspect safecontext-api --format '{{index .Config.Labels "version"}}').tar.gz .env docker-compose.yml
```

### Paso 1: Transferir nuevo bundle

```bash
scp safecontext-bundle-N+1.tar.gz operator@airgapped-host:/opt/safecontext/
```

### Paso 2: Cargar nuevas imágenes

```bash
tar -xzf safecontext-bundle-N+1.tar.gz
for img in safecontext-bundle-N+1/images/*.tar; do docker load -i "$img"; done
```

### Paso 3: Actualizar configuración si hay cambios en .env.example

### Paso 4: Aplicar migraciones de base de datos (OBLIGATORIO desde F2)

El esquema de BD tiene 4 migraciones acumuladas (0001-0004):
- 0001: Schema inicial
- 0002: approved_by_agent_id en redactions
- 0003: Índice JSONB en outbox.payload->>'operation_id'
- 0004: Operation.sanitized_text + índice artifact_digest

```bash
docker compose run --rm api alembic upgrade head
```

### Paso 5: Reemplazar servicios con rolling update

```bash
docker compose up -d --no-deps api worker ui
```

### Verificación

```bash
curl http://localhost/health
docker compose ps
```

## Rollback si el upgrade falla

```bash
./infra/scripts/rollback.sh safecontext-bundle-N.tar.gz
```
