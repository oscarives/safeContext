# ADR-011 · Port & Adapter pattern para Redis y MinIO
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Las licencias de Redis 8 (tri-license) y MinIO Community Edition (AGPLv3) están bajo revisión legal. Se necesita aislar estas dependencias para que un cambio de edición o proveedor tenga impacto mínimo en el código de negocio.

## Decisión
Redis y MinIO se usan exclusivamente a través de **puertos (interfaces)**. Las implementaciones concretas son adapters intercambiables.

```
BrokerPort       → RedisBrokerAdapter     (swap: RabbitMQBrokerAdapter)
CachePort        → RedisCacheAdapter      (swap: MemcachedCacheAdapter)
StoragePort      → S3StorageAdapter       (usa boto3 + endpoint MinIO)
                                           (swap: apuntar a AIStor, S3 nativo, etc.)
```

## Consecuencias
- El código de negocio (workers, API) nunca importa `redis` o `boto3` directamente.
- Cambiar de Redis 7 → Redis 8, o de MinIO CE → AIStor, requiere solo:
  1. Actualizar el adapter correspondiente (o parámetros de configuración).
  2. Cambiar variables de entorno.
- El selector de adapter es configuración: `BROKER_ADAPTER=redis`, `STORAGE_ADAPTER=minio`.

## Ubicación
- `workers/core/ports.py` — definiciones de BrokerPort, CachePort, StoragePort
- `workers/adapters/` — implementaciones concretas
