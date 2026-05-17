# Deploy Gate: GitHub Deployment Protection Rules

**Fase**: F3 · **Estado**: documentado (activar al agregar remote)

---

## Configuración requerida en GitHub

Una vez que el repositorio tenga un remote en GitHub, configurar en
**Settings → Environments → production**:

### 1. Required reviewers
- Agregar al menos 1 revisor designado (Tech Lead o Compliance)
- Cualquier deploy a `production` requiere su aprobación explícita

### 2. Wait timer
- Configurar 5 minutos de espera mínima entre aprobación y ejecución
- Permite cancelar deploys aprobados accidentalmente

### 3. Branch protection
En **Settings → Branches → main**:
- `Require pull request before merging`
- `Require status checks to pass`: `detect-secrets`, `lint-python`, `test-api`, `test-opa`
- `Require branches to be up to date before merging`
- `Restrict who can push to matching branches`

---

## Flujo de deploy gate (E3.3)

```
Commit a main
    │
    ▼
CI pipeline (ci.yml)
    ├── detect-secrets ──────── 0 hallazgos → continúa
    ├── lint-python
    ├── test-api
    ├── test-opa ────────────── coverage ≥ 80% → continúa
    └── safecontext-gate ─────── no hallazgos críticos → continúa
    │
    ▼
Build, Sign & Attest (build-sign.yml)
    ├── Trivy fs scan ────────── 0 CRITICAL CVEs → continúa
    ├── Syft SBOM generation
    ├── Docker build + push
    ├── Trivy image scan ──────── 0 CRITICAL CVEs → continúa
    ├── cosign sign ──────────── firma keyless OIDC
    ├── cosign attest SBOM
    └── SLSA provenance
    │
    ▼
Deploy Gate (deploy.yml)
    ├── verify-signatures ────── cosign verify + attestation → continúa
    ├── scan-images (final) ───── Trivy CRITICAL → bloquea si hay CVEs
    └── deploy-production
          │
          ▼
        ⏸ HUMAN APPROVAL REQUIRED (GitHub environment gate)
          │
          ▼ (aprobado por revisor designado)
        kubectl rollout + evidencia registrada
```

## Excepciones a políticas (criterio E3.3)

Toda excepción requiere:
1. Ejecutar `exception.yml` manualmente (workflow_dispatch)
2. Rellenar: justificación, componente afectado, CVE/finding ID
3. Aprobación del mismo gate de producción (mismo revisor)
4. Registro automático en `docs/exceptions/EXC_YYYYMMDD_HHMMSS.md` con `trace_id`

**Ninguna excepción puede proceder sin aprobador registrado.**
