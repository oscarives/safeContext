# ADR-002 · Redis exclusivamente como broker y cache efímero
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Next.js en multi-instancia requiere un cache compartido. Dramatiq necesita un broker de mensajes. Redis cubre ambos casos pero no debe convertirse en fuente de verdad.

## Decisión
Redis no almacena ningún estado que no pueda perderse. Solo actúa como:
1. Broker de Dramatiq (mensajes de trabajo)
2. Cache de Next.js (respuestas HTTP cacheadas)

## Consecuencias
- El cache handler de Next.js apunta a Redis, no a disco local (requerido para multi-instancia consistente).
- `FLUSHALL` en Redis no debe causar pérdida de datos de negocio.
- Implementación aislada detrás de `BrokerPort` y `CachePort` (ver ADR-011).
