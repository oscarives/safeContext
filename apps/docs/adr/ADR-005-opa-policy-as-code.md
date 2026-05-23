# ADR-005 · OPA/Rego para policy-as-code
**Estado**: Cerrado · **Fecha**: 2026-05-17

## Contexto
Las reglas de detección, sanitización y autorización deben ser versionables, testeables e independientes del ciclo de release de la aplicación.

## Decisión
Todas las reglas de detección, sanitización y autorización son **políticas OPA/Rego** en `/policies/`.

## Consecuencias
- Las políticas se despliegan por pipeline, no por release de la aplicación.
- Hot-reload de políticas sin reinicio de workers (desde F2).
- `policy_version` en cada decisión corresponde a versión semver en repositorio.
- `opa test` con ≥ 80% de cobertura es gate de CI desde F1.

## Alternativa rechazada
Reglas hardcodeadas en Python — no versionables, no auditables, no testeables de forma independiente.

## Extensiones implementadas (2026-05-23)

### Waiver-aware decisions
La funcion `decision()` ahora delega a `decision_with_waivers(findings, waivers)` que filtra hallazgos waived antes de evaluar. Mantiene backward-compat: `decision(findings)` equivale a `decision_with_waivers(findings, [])`.

Funciones agregadas en `safecontext.rego`:
- `should_waive(finding, waivers)` — true si algun waiver activo matchea `rule_id` + `entity_pattern` (regex)
- `active_findings_after_waivers(findings, waivers)` — subset de findings no waived
- `decision_with_waivers(findings, waivers)` — decision consolidada con campo `waived_count`

Respuesta de `decision_with_waivers`:
```json
{
  "allow": true,
  "requires_human_review": false,
  "policy_version": "1.0.0",
  "findings_count": 1,
  "waived_count": 2,
  "critical_count": 0
}
```

Cobertura: 9 tests adicionales en `safecontext_test.rego` (waiver block, review, inactive, regex mismatch, counts, backward compat, partial, all waived).
