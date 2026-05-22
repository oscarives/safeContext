# ADR-008 · MinIO con WORM + SSE para almacenamiento de artefactos
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Los artefactos de evidencia (documentos originales, documentos sanitizados, export de audit trail) deben ser inmutables y cifrados. Se necesita almacenamiento S3-compatible para compatibilidad con entornos cloud y air-gapped.

## Decisión
MinIO Community Edition (AGPLv3) con object locking (WORM) y cifrado del lado servidor (SSE). Implementado detrás de `StoragePort` (ver ADR-011).

## Consecuencias
- Los artefactos son inmutables una vez almacenados — cualquier corrección genera nueva versión.
- `StoragePort` usa la S3 API (boto3) — swap a AIStor o S3 nativo solo requiere cambio de endpoint en `.env`.
- Decisión explícita de edición requerida antes de F3 (análisis legal AGPLv3).

## Actualización — 2026-05-22

El repositorio público de MinIO CE fue archivado en abril 2026. La decisión de continuidad y ruta de upgrade a AIStor está documentada en **ADR-013**. El código no requiere cambios — ADR-011 ya garantiza el aislamiento.
