# Runbook: Disaster Recovery

**Versión**: 1.0.0 · **Último drill**: pendiente (programar antes de F4)
**RTO objetivo**: < 1 hora · **RPO objetivo**: < 5 minutos (con WAL archiving)

## 1. Escenarios cubiertos

| Escenario | RTO estimado |
|---|---|
| Fallo de PostgreSQL (datos corruptos) | 30-45 min |
| Fallo de MinIO (pérdida de artefactos) | 15-20 min |
| Fallo completo del host | 45-60 min |

## 2. Pre-requisitos

- Acceso al directorio de backups: `/backups/postgres/`
- Acceso a MinIO backup bucket: `safecontext-artifacts-backup`
- Variables de entorno del stack disponibles

## 3. Restore de PostgreSQL

### Paso 1: Identificar backup disponible más reciente
```bash
ls -la /backups/postgres/
# Seleccionar el directorio más reciente: YYYYMMDD_HHMMSS
```

### Paso 2: Detener el stack (excepto postgres para el restore)
```bash
docker compose stop api worker ui
```

### Paso 3: Ejecutar restore
```bash
docker compose exec postgres /pg-restore.sh <TIMESTAMP>
# Ejemplo: docker compose exec postgres /pg-restore.sh 20260617_030000
```

### Paso 4: Verificar integridad post-restore
```bash
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT count(*) FROM operations;"
```

### Paso 5: Reiniciar el stack
```bash
docker compose start api worker ui
curl http://localhost/health
```

### Verificación de éxito
- `GET /health` retorna `{"status": "ok"}`
- `SELECT count(*) FROM operations` coincide con valor pre-fallo (si hay log)

## 4. Restore de MinIO

```bash
# Re-sincronizar desde backup bucket
docker compose exec minio mc mirror \
  local/safecontext-artifacts-backup \
  local/safecontext-artifacts
```

## 5. Programación de drills

| Frecuencia | Tipo | Responsable |
|---|---|---|
| Trimestral | DR drill completo (pasos 1-5) | Operador |
| Mensual | Verificar backups disponibles | Operador |
| En cada deploy | Smoke test de /health | CI/CD |

## 6. Post-drill: evidencia requerida

Completar y guardar en `/docs/drills/DR_DRILL_YYYYMMDD.md`:
- Timestamp de inicio y fin del drill
- RTO obtenido
- Backup utilizado (timestamp)
- Resultado de verificación de integridad
- Incidencias encontradas
