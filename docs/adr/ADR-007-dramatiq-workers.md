# ADR-007 · Dramatiq sobre Redis como broker de workers
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Los agentes internos (Detector, Sanitizador, etc.) necesitan un sistema de procesamiento asíncrono con reintentos, DLQ y garantías de entrega.

## Decisión
Dramatiq como framework de workers con Redis como broker (vía `BrokerPort` — ver ADR-011).

## Consecuencias
- Todos los workers deben ser **idempotentes** desde F1 — el broker puede re-entregar mensajes.
- DLQ configurada desde F1: mensajes fallidos después de 3 reintentos van a `safecontext_dl`.
- Graceful shutdown implementado desde F2.

## Umbral de migración a Celery
Si en F2/F3 se requieren chord/group/chain o scheduling complejo, se reevalúa.
