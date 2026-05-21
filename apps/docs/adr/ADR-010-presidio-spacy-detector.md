# ADR-010 · Presidio + spaCy como detectores base, interfaz abstraída
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
La detección de PII y secretos requiere NLP/ML. Las herramientas evolucionan y los clientes enterprise pueden querer aportar sus propios detectores.

## Decisión
Los detectores implementan una interfaz común (`DetectorInterface`). Presidio/spaCy son la implementación por defecto, reemplazables por detector custom sin cambiar la capa de agentes.

## Consecuencias
- El worker Detector no sabe qué librería usa internamente.
- Recall se evalúa contra la interfaz — no contra la implementación.
- Gate de recall en CI desde F1: ≥ 0.90 (F1), ≥ 0.95 (F2), ≥ 0.98 (F5).
- Los modelos nunca se descargan en runtime — deben estar en imagen o volumen local.
