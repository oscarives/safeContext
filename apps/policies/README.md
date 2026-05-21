# SafeContext OPA Policies

This directory contains the Open Policy Agent (OPA) policies that govern SafeContext's
document sanitization and data-governance pipeline.

## Directory structure

```
policies/
├── base/
│   ├── safecontext.rego        # Main policy (package safecontext.policy)
│   ├── safecontext_test.rego   # OPA unit tests
│   └── metadata.json           # Semver policy version and entity-class catalogue
└── README.md                   # This file
```

## Policy overview

Package: `safecontext.policy`  
Current version: `1.0.0` (see `base/metadata.json`)

The base policy evaluates a list of `findings` (detected sensitive entities) and returns:

| Rule | Description |
|------|-------------|
| `decision(findings)` | Consolidated decision object for an operation |
| `should_block(findings)` | True when a critical finding exceeds its confidence threshold |
| `operation_requires_review(findings)` | True when any finding requires human review |
| `requires_review(finding)` | True when confidence < class threshold OR severity == "critical" |
| `effective_severity(finding)` | Downgraded to "low" when confidence < 0.50, otherwise the class base severity |

Entity classes and their thresholds/severities:

| Entity class | Confidence threshold | Base severity |
|---|---|---|
| EMAIL_ADDRESS | 0.85 | medium |
| PHONE_NUMBER | 0.80 | medium |
| PERSON | 0.85 | medium |
| API_KEY | 0.95 | critical |
| PASSWORD | 0.95 | critical |
| CREDIT_CARD | 0.90 | high |
| SSN | 0.85 | critical |
| IBAN_CODE | 0.85 | high |
| IP_ADDRESS | 0.75 | low |
| MEDICAL_RECORD | 0.85 | critical |

## 1. Start OPA server

```bash
opa run --server --addr :8181 policies/
```

OPA will load all `.rego` files under `policies/` and serve them via HTTP at port 8181.

## 2. Query the policy

Send a list of findings to the `decision` endpoint:

```bash
curl -X POST http://localhost:8181/v1/data/safecontext/policy/decision \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "findings": [
        {
          "entity_type": "API_KEY",
          "confidence": 0.97,
          "severity": "critical"
        }
      ]
    }
  }'
```

Expected response structure:

```json
{
  "result": {
    "allow": false,
    "requires_human_review": true,
    "policy_version": "1.0.0",
    "findings_count": 1,
    "critical_count": 1
  }
}
```

Query individual rules (e.g. `should_block`):

```bash
curl -X POST http://localhost:8181/v1/data/safecontext/policy/should_block \
  -H "Content-Type: application/json" \
  -d '{"input": {"findings": [{"entity_type": "SSN", "confidence": 0.90, "severity": "critical"}]}}'
```

## 3. Run tests

```bash
opa test policies/ -v
```

Expected output: all tests in `safecontext_test.rego` pass.

## 4. Verify coverage

```bash
opa test policies/ --coverage
```

Target: >= 80% rule coverage across `policies/base/safecontext.rego`.

## 5. Validate policy syntax

```bash
opa check policies/
```

## Version management

The `policy_version` constant in `safecontext.rego` must always match the `"version"` field
in `base/metadata.json`. Both must be updated together when the policy changes.
