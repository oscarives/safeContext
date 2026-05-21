# Runbook: DLQ Recovery

## Síntomas
Alerta `DLQDepthHigh` activa. Mensajes en `safecontext_dl` después de 3 reintentos fallidos.

## Diagnóstico
1. Ver mensajes en DLQ: `redis-cli LRANGE safecontext_dl 0 -1`
2. Identificar causa: revisar logs del worker con el `operation_id` del mensaje
3. Verificar conectividad: `GET /health` en la API

## Recuperación
1. Corregir causa raíz (BD, MinIO, OPA)
2. Re-encolar mensajes: script `infra/scripts/dlq-requeue.sh`
3. Verificar que `safecontext_dlq_depth` vuelve a 0

## Prevención
- Configurar alertas de conectividad a dependencias
- Monitorizar `safecontext_operations_total{status="pending"}` > umbral
