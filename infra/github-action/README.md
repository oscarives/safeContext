# SafeContext GitHub Action

Scans documents and code context for PII, secrets and sensitive data using SafeContext as a pipeline security gate.

## Usage

```yaml
# .github/workflows/security-gate.yml
name: Security Gate

on: [push, pull_request]

jobs:
  safecontext-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: SafeContext Security Gate
        uses: safecontext/action@v1
        with:
          api-url: ${{ secrets.SAFECONTEXT_API_URL }}
          token: ${{ secrets.SAFECONTEXT_TOKEN }}
          document-path: "."
          policy-name: "base"
          fail-on-severity: "high"
          post-comment: "true"
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `api-url` | ✅ | — | SafeContext API base URL |
| `token` | ✅ | — | Bearer token for MCP authentication |
| `document-path` | ❌ | `.` | File or directory to scan |
| `policy-name` | ❌ | `base` | OPA policy name |
| `fail-on-severity` | ❌ | `high` | Minimum severity that blocks pipeline |
| `post-comment` | ❌ | `true` | Post findings as PR comment |

## Outputs

| Output | Description |
|---|---|
| `trace-id` | SafeContext trace_id for audit trail |
| `findings-count` | Number of findings detected |
| `result` | `pass` or `block` |

## Exit codes

- **0** — No findings at or above `fail-on-severity` threshold
- **1** — Findings detected at or above threshold (pipeline blocked)

## Note: local-only repository

This action requires a network-accessible SafeContext API endpoint.
When the repository has no remote, the action files are ready for use
once a remote is added and the API is deployed.
