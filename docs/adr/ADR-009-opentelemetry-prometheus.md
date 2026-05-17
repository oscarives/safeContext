# ADR-009 · OpenTelemetry + Prometheus para observabilidad
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Se necesita observabilidad completa del flujo API → worker → DB → MinIO sin lock-in a un vendor específico.

## Decisión
- **OTel**: trazas distribuidas con propagación de trace_id en todo el flujo.
- **Prometheus**: métricas de servicio y de calidad de detección.
- Sin vendor lock-in — exporters intercambiables.

## Consecuencias
- Cada componente se instrumenta desde F1. La observabilidad no es un afterthought.
- Métricas de recall por clase de detector son métricas de primera clase desde F1.
- `trace_id` es el hilo que conecta logs, trazas y audit trail.
