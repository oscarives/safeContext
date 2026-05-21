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
