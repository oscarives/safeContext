# ADR-004 · Agentes internos como única fuente de capacidad
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Múltiples superficies de consumo (UI, MCP, pipeline CI/CD) necesitan las mismas capacidades de detección, sanitización y auditoría.

## Decisión
Detector, Sanitizador, Clasificador, Auditor y Revisor son **workers internos**. UI y MCP invocan los mismos workers. No existe lógica de negocio duplicada por superficie.

## Consecuencias
- Agregar una nueva superficie (CLI, webhook) no requiere reimplementar capacidades.
- La UI no procesa documentos — es un cliente de los mismos agentes que usa el MCP Server.
- Toda la lógica de negocio vive en `/workers/`.
