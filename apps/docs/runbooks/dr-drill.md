# Runbook: DR Drill (Enterprise — RTO < 15 min)

**Versión**: 1.0.0
**Tipo**: Trimestral · **RTO objetivo**: < 15 minutos
**Diferencia de dr.md**: este runbook es para el drill formal con medición de RTO.

## Preparación (1 semana antes)

- [ ] Notificar al equipo de la ventana de drill (no en horas pico)
- [ ] Verificar que el último backup automático tiene < 24h
- [ ] Preparar entorno de prueba aislado
- [ ] Tener este runbook impreso o en dispositivo separado

## Ejecución del drill

### T+0:00 — Inicio (registrar timestamp exacto)
```bash
echo "DRILL START: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee /tmp/drill-log.txt
```

### T+0:01 — Simular falla (detener postgres)
```bash
docker compose stop postgres
echo "T+0:01 postgres stopped" >> /tmp/drill-log.txt
```

### T+0:02 — Verificar detección
```bash
curl -s http://localhost/health | python -m json.tool
echo "T+0:02 health check result above" >> /tmp/drill-log.txt
```

### T+0:03 — Identificar backup más reciente
```bash
ls -lt /var/lib/docker/volumes/safecontext_pg_backups/_data/ | head -3
# Anotar TIMESTAMP del backup a restaurar
echo "T+0:03 backup timestamp: <ANOTAR>" >> /tmp/drill-log.txt
```

### T+0:05 — Iniciar restore
```bash
docker compose up -d postgres
docker compose exec postgres /pg-restore.sh <TIMESTAMP>
echo "T+0:05 restore started" >> /tmp/drill-log.txt
```

### T+0:12 — Verificar integridad
```bash
docker compose exec postgres psql -U safecontext_app -d safecontext \
  -c "SELECT count(*), max(created_at) FROM operations;"
echo "T+0:12 integrity check above" >> /tmp/drill-log.txt
```

### T+0:13 — Reiniciar servicios dependientes
```bash
docker compose start api worker
echo "T+0:13 services restarted" >> /tmp/drill-log.txt
```

### T+0:14 — Verificar recuperación
```bash
curl -s http://localhost/health
echo "T+0:14 final health check" >> /tmp/drill-log.txt
echo "DRILL END: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> /tmp/drill-log.txt
```

## Registro de evidencia post-drill

Copiar `/tmp/drill-log.txt` a `docs/drills/DR_DRILL_YYYYMMDD.md` con:
- RTO total (T_END - T_START)
- Número de operaciones verificadas post-restore
- Incidencias encontradas
- Firma del operador responsable

## Calendario de drills
| Trimestre | Fecha tentativa | Responsable |
|---|---|---|
| Q3 2026 | Semana del 2026-08-10 | Operador |
| Q4 2026 | Semana del 2026-11-09 | Operador |
| Q1 2027 | Semana del 2027-02-09 | Operador |
