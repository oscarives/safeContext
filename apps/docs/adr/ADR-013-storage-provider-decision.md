# ADR-013 · Decisión de proveedor de storage post-archival de MinIO CE

**Estado**: Aceptado · **Fecha**: 2026-05-22  
**Reemplaza**: actualización de ADR-008 · **Relacionado**: ADR-011

---

## Contexto

En abril de 2026, el repositorio público de MinIO Community Edition fue archivado por sus mantenedores. El proyecto SafeContext usa MinIO CE como implementación concreta del `StoragePort` (ADR-011) para almacenamiento WORM + SSE de artefactos.

**Implicaciones del archival**:
- No habrá nuevas versiones ni parches de seguridad para MinIO CE
- La licencia AGPLv3 no cambia — las versiones existentes siguen siendo usables
- La imagen Docker existente (`minio/minio:RELEASE.2025-09-07`) sigue funcionando
- AIStor (fork comercial de los creadores originales de MinIO) es el sucesor designado

**Evaluación de alternativas**:

| Alternativa | API S3 | WORM | SSE | Air-gapped | Licencia | Esfuerzo de swap |
|---|---|---|---|---|---|---|
| **MinIO CE (pinned)** | ✅ | ✅ | ✅ | ✅ | AGPLv3 | 0 — estado actual |
| **AIStor** (fork MinIO) | ✅ | ✅ | ✅ | ✅ | Comercial | Solo `.env` — ADR-011 abstrae |
| **Garage** (Rust, OSS) | ✅ | ⚠️ (parcial) | ✅ | ✅ | AGPL-3.0 | Solo `.env` |
| **SeaweedFS** | ✅ | ❌ | ⚠️ | ✅ | Apache 2.0 | Solo `.env` (sin WORM) |
| **AWS S3** | ✅ | ✅ | ✅ | ❌ | SaaS | Solo `.env` — rompe air-gap |
| **Ceph RGW** | ✅ | ✅ | ✅ | ✅ | LGPL-2.1 | Solo `.env` — operación compleja |

---

## Decisión

**Mantener MinIO CE pinned a `RELEASE.2025-09-07`** (última release estable pre-archival) para todos los entornos hasta el primer cliente enterprise real.

**Ruta de upgrade documentada**: AIStor cuando se requiera soporte comercial o parches de seguridad post-archival.

**El `StoragePort` (ADR-011) ya garantiza que el swap = solo variables de entorno**:
```bash
# Hoy (MinIO CE)
STORAGE_ADAPTER=minio
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=<key>
S3_SECRET_KEY=<secret>

# Upgrade a AIStor (sin cambios de código)
STORAGE_ADAPTER=s3_compatible
S3_ENDPOINT=https://aisstor.internal:9000
S3_ACCESS_KEY=<aisstor_key>
S3_SECRET_KEY=<aisstor_secret>
```

---

## Rationale

1. **Riesgo bajo en el corto plazo**: la imagen pinned sigue funcionando correctamente. El archival no es un zero-day — es una señal de roadmap.
2. **Cero esfuerzo de código**: ADR-011 ya abstrae correctamente. Cambiar de proveedor no toca ninguna línea de lógica de negocio.
3. **AIStor como sucesor natural**: mismos creadores, misma API S3, soporte comercial disponible. Garage es una alternativa OSS viable pero no tiene WORM completo.
4. **Air-gap es requisito no negociable** (ADR-006): AWS S3 descartado.

---

## Consecuencias

- **Inmediato**: pinear explícitamente `minio/minio:RELEASE.2025-09-07` en `docker-compose.yml` e imágenes K8s (si no está ya).
- **Antes del primer cliente enterprise**: evaluar AIStor pricing/SLA y ejecutar swap (estimado: ½ día de operaciones).
- **Variables de entorno**: renombrar `MINIO_*` → `S3_*` en `.env.example` para reflejar la abstracción. El adapter interno sigue usando el mismo endpoint.
- **No hay urgencia de código**: la abstracción ya existe. Esta ADR cierra la deuda de due diligence.

---

## Referencias

- ADR-008 — Decisión original de MinIO WORM + SSE
- ADR-011 — Port & Adapter pattern (StoragePort)
- `workers/adapters/` — S3StorageAdapter (implementación concreta intercambiable)
- `.env.example` — variables de entorno actualizadas con ruta de upgrade
