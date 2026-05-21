# ADR-006 · Docker Compose para desarrollo; Kubernetes para Enterprise/HA
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
El stack tiene múltiples componentes con dependencias. Se necesita un modelo de despliegue que sea simple para desarrollo y escalable para producción enterprise.

## Decisión
- **F1–F2**: Docker Compose (single-node) como único modelo de despliegue.
- **F3+**: Manifiestos Kubernetes generados desde Compose Bridge.

## Umbral de migración a K8s
Cuando cualquiera de estas condiciones se cumple: multi-instancia requerida, HPA necesario, multi-tenant, exigencia regulatoria formal de HA.

## Consecuencias
- No se mantienen dos configuraciones manuales — Compose Bridge genera los manifiestos K8s.
- El stack de desarrollo y el de producción son estructuralmente idénticos.
