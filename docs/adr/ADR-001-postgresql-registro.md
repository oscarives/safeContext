# ADR-001 · PostgreSQL como único sistema de registro
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Redis ofrece mayor velocidad pero usa replicación asíncrona con ventanas de pérdida de datos. Se necesita garantía de durabilidad para decisiones de sanitización, auditoría y jobs.

## Decisión
PostgreSQL es la **única fuente de verdad** para decisiones, jobs, auditoría y estado durable. Redis es broker efímero.

## Consecuencias
- Los workers usan el patrón outbox: escriben en `outbox` de PostgreSQL antes de encolar en Redis.
- Si Redis pierde mensajes, PostgreSQL permite reencolar desde `outbox WHERE processed = false`.
- Ningún estado de negocio vive solo en Redis.

## Alternativa rechazada
Redis como registro de jobs — riesgo de pérdida de evidencia ante partición o failover.
