# ADR-003 · MCP Server implementado sobre FastAPI
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
MCP requiere un servidor que exponga tools con schemas definidos, autenticación y streaming de respuestas.

## Decisión
El MCP Server es un **módulo de FastAPI** — no un proceso separado. Comparte autenticación, observabilidad y acceso a agentes internos.

## Consecuencias
- Versionado de tools MCP se gestiona como versionado de endpoints REST (`/v1/mcp/tools`).
- Un solo proceso sirve tanto la REST API como el MCP Server.

## Riesgo y mitigación
Si MCP spec evoluciona con breaking changes, el módulo requiere actualización. Mitigación: abstracción de protocolo desde F1; versionado de tools desde F4.
