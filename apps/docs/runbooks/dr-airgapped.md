# Runbook: DR Drill Air-Gapped (F5)

**Versión**: 1.0.0 · **Fase**: F5 · **RTO objetivo**: < 15 min sin internet

## Prerrequisitos para el drill

- [ ] Entorno de prueba sin acceso a internet (iptables/firewall configurado)
- [ ] Bundle de la versión actual disponible en `/opt/safecontext/bundles/`
- [ ] Backup de PostgreSQL con WAL disponible en `/backups/postgres/`
- [ ] Herramienta para verificar ausencia de internet: `curl -sf https://1.1.1.1 || echo "NO INTERNET"`

## Verificar entorno aislado

```bash
# Confirmar que no hay internet
curl -sf --connect-timeout 3 https://1.1.1.1 >/dev/null 2>&1 \
  && echo "FAIL: internet still reachable" \
  || echo "OK: air-gapped confirmed"

# Confirmar Harbor disponible localmente
curl -sf http://localhost:5000/v2/ && echo "Harbor: OK"
```

## Pasos del drill (objetivo: RTO < 15 min)

### T+0:00 — Inicio del drill
```bash
DRILL_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "DRILL START: $DRILL_START" | tee /tmp/drill-airgapped.log
echo "Environment: air-gapped" >> /tmp/drill-airgapped.log
```

### T+0:01 — Simular falla total del stack
```bash
docker compose down --timeout 30
echo "T+0:01 stack stopped" >> /tmp/drill-airgapped.log
```

### T+0:02 — Instalar desde bundle (sin internet)
```bash
LATEST_BUNDLE=$(ls -t /opt/safecontext/bundles/*.tar.gz | head -1)
echo "T+0:02 installing from bundle: $LATEST_BUNDLE" >> /tmp/drill-airgapped.log
./infra/scripts/install-bundle.sh "$LATEST_BUNDLE"
```

### T+0:05 — Restore de PostgreSQL
```bash
LATEST_BACKUP=$(ls -t /backups/postgres/ | head -1)
echo "T+0:05 restoring PG from: $LATEST_BACKUP" >> /tmp/drill-airgapped.log
docker compose run --rm pg-backup /pg-restore.sh "$LATEST_BACKUP"
```

### T+0:08 — Levantar stack completo desde Harbor local
```bash
# Todas las imágenes vienen de Harbor (sin internet)
docker compose up -d
echo "T+0:08 stack starting" >> /tmp/drill-airgapped.log
```

### T+0:11 — Verificar integridad
```bash
docker compose ps
curl -sf http://localhost/health | python -m json.tool
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT count(*), max(created_at) FROM operations;"
echo "T+0:11 integrity verified" >> /tmp/drill-airgapped.log
```

### T+0:13 — Verificar recall de modelos offline
```bash
docker compose exec worker python -c "
from workers.ml.model_loader import verify_models_available
r = verify_models_available()
for m, ok in r.items():
    print(f'{m}: {\"OK\" if ok else \"MISSING\"}')"
echo "T+0:13 models verified" >> /tmp/drill-airgapped.log
```

### T+0:14 — Confirmar ausencia de internet durante todo el drill
```bash
# No request should have gone out
curl -sf --connect-timeout 3 https://1.1.1.1 >/dev/null 2>&1 \
  && echo "FAIL: internet was reachable" \
  || echo "OK: no internet used during drill"
DRILL_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "DRILL END: $DRILL_END" >> /tmp/drill-airgapped.log
```

## Registro de evidencia post-drill

Copiar a `docs/drills/DR_AIRGAPPED_YYYYMMDD.md`:
- RTO total
- Backup utilizado (timestamp)
- Versión del bundle
- Resultado `verify_models_available()`
- Resultado de `GET /health`
- Firma del operador

## Criterios de éxito del drill

| Criterio | Verificación |
|---|---|
| Sin acceso a internet | `curl 1.1.1.1` falla en T+0:00 y T+0:14 |
| RTO < 15 min | `DRILL_END - DRILL_START` < 900 segundos |
| Stack saludable | `GET /health` retorna `{"status": "ok"}` |
| Modelos offline | `verify_models_available()` todos `OK` |
| Datos recuperados | `count(*) FROM operations` > 0 |

## Frecuencia

Trimestral, coordinado con el DR drill estándar (ver `dr-drill.md`).
