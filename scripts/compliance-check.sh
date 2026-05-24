#!/usr/bin/env bash
# compliance-check.sh — Automated compliance verification suite
#
# Runs 5 checks and generates a consolidated JSON report:
#   1. CIS Docker Benchmark (Dockerfile lint via hadolint)
#   2. Secrets scan (detect-secrets)
#   3. Dependency audit (pip-audit + npm audit)
#   4. License compliance (pip-licenses)
#   5. OWASP dependency-check (safety / pip-audit CVE scan)
#
# Usage:
#   ./scripts/compliance-check.sh              # Run all checks
#   ./scripts/compliance-check.sh --check 2    # Run only check 2
#   ./scripts/compliance-check.sh --ci         # CI mode: exit 1 on critical
#
# Output: compliance-report.json in repo root

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_FILE="${REPO_ROOT}/compliance-report.json"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CI_MODE=false
SINGLE_CHECK=""
HAS_CRITICAL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ci) CI_MODE=true; shift ;;
    --check) SINGLE_CHECK="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 2 ;;
  esac
done

RESULTS=()

add_result() {
  local check_id="$1" check_name="$2" status="$3" details="$4" findings_count="${5:-0}"
  [[ "$status" == "critical" ]] && HAS_CRITICAL=true
  RESULTS+=("{\"check_id\":${check_id},\"check_name\":\"${check_name}\",\"status\":\"${status}\",\"findings_count\":${findings_count},\"details\":\"${details}\"}")
}

should_run() { [[ -z "$SINGLE_CHECK" ]] || [[ "$SINGLE_CHECK" == "$1" ]]; }

# ── Check 1: CIS Docker Benchmark (Dockerfile lint) ───────────────────
if should_run 1; then
  echo "=== Check 1: CIS Docker Benchmark ==="
  if command -v hadolint &>/dev/null; then
    ISSUES=0
    for df in $(find "${REPO_ROOT}" -name "Dockerfile*" -not -path "*/node_modules/*" 2>/dev/null); do
      ISSUES=$((ISSUES + $(hadolint "$df" 2>&1 | wc -l || true)))
    done
    if [[ $ISSUES -eq 0 ]]; then
      add_result 1 "CIS Docker Benchmark" "pass" "All Dockerfiles pass hadolint" 0
    else
      add_result 1 "CIS Docker Benchmark" "warn" "${ISSUES} hadolint issues" "$ISSUES"
    fi
  else
    DOCKER_ISSUES=0
    for df in $(find "${REPO_ROOT}" -name "Dockerfile*" -not -path "*/node_modules/*" 2>/dev/null); do
      grep -q "^USER" "$df" 2>/dev/null || DOCKER_ISSUES=$((DOCKER_ISSUES + 1))
      grep -q "^HEALTHCHECK" "$df" 2>/dev/null || DOCKER_ISSUES=$((DOCKER_ISSUES + 1))
    done
    [[ $DOCKER_ISSUES -eq 0 ]] \
      && add_result 1 "CIS Docker Benchmark" "pass" "Basic Dockerfile checks pass" 0 \
      || add_result 1 "CIS Docker Benchmark" "warn" "${DOCKER_ISSUES} best-practice issues" "$DOCKER_ISSUES"
  fi
fi

# ── Check 2: Secrets scan ──────────────────────────────────────────────
if should_run 2; then
  echo "=== Check 2: Secrets scan ==="
  if command -v detect-secrets &>/dev/null; then
    SECRET_COUNT=$(detect-secrets scan --baseline "${REPO_ROOT}/.secrets.baseline" 2>&1 | grep -c "True" 2>/dev/null || echo 0)
    [[ "$SECRET_COUNT" -eq 0 ]] \
      && add_result 2 "Secrets scan" "pass" "No new secrets detected" 0 \
      || add_result 2 "Secrets scan" "critical" "${SECRET_COUNT} potential secrets" "$SECRET_COUNT"
  else
    BASIC=$(grep -rn --include="*.py" --include="*.ts" --include="*.js" --include="*.yml" \
      -E "(AKIA[A-Z0-9]{16}|sk-[a-zA-Z0-9]{32,}|-----BEGIN (RSA )?PRIVATE KEY-----)" \
      "${REPO_ROOT}/apps/" 2>/dev/null | grep -cv "test\|mock\|fake\|example" || echo 0)
    [[ "$BASIC" -eq 0 ]] \
      && add_result 2 "Secrets scan" "pass" "No hardcoded secrets (basic scan)" 0 \
      || add_result 2 "Secrets scan" "critical" "${BASIC} potential secrets" "$BASIC"
  fi
fi

# ── Check 3: Dependency audit ──────────────────────────────────────────
if should_run 3; then
  echo "=== Check 3: Dependency audit ==="
  DEP_ISSUES=0; DEP_STATUS="pass"; DEP_DETAILS=""
  if command -v pip-audit &>/dev/null; then
    PIP_VULNS=$(pip-audit --format json -r "${REPO_ROOT}/apps/api/requirements.txt" 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('dependencies',d) if isinstance(d,dict) else d))" 2>/dev/null || echo 0)
    [[ "$PIP_VULNS" -gt 0 ]] && { DEP_ISSUES=$((DEP_ISSUES + PIP_VULNS)); DEP_STATUS="warn"; }
    DEP_DETAILS="pip-audit: ${PIP_VULNS} vulnerable"
  else
    DEP_DETAILS="pip-audit not installed"; DEP_STATUS="skipped"
  fi
  if command -v npm &>/dev/null && [[ -f "${REPO_ROOT}/apps/ui/package-lock.json" ]]; then
    NPM_VULNS=$(cd "${REPO_ROOT}/apps/ui" && npm audit --json 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); v=d.get('metadata',{}).get('vulnerabilities',{}); print(v.get('high',0)+v.get('critical',0))" 2>/dev/null || echo 0)
    [[ "$NPM_VULNS" -gt 0 ]] && { DEP_ISSUES=$((DEP_ISSUES + NPM_VULNS)); DEP_STATUS="critical"; }
    DEP_DETAILS="${DEP_DETAILS}; npm high/critical: ${NPM_VULNS}"
  fi
  add_result 3 "Dependency audit" "$DEP_STATUS" "$DEP_DETAILS" "$DEP_ISSUES"
fi

# ── Check 4: License compliance ────────────────────────────────────────
if should_run 4; then
  echo "=== Check 4: License compliance ==="
  if command -v pip-licenses &>/dev/null; then
    BAD=$(pip-licenses --format=csv 2>/dev/null | grep -cE "AGPL|SSPL|BUSL|Elastic" || echo 0)
    [[ "$BAD" -eq 0 ]] \
      && add_result 4 "License compliance" "pass" "No restricted licenses" 0 \
      || add_result 4 "License compliance" "warn" "${BAD} restricted licenses" "$BAD"
  else
    add_result 4 "License compliance" "skipped" "pip-licenses not installed" 0
  fi
fi

# ── Check 5: OWASP dependency-check ───────────────────────────────────
if should_run 5; then
  echo "=== Check 5: OWASP dependency check ==="
  if command -v safety &>/dev/null; then
    SAFETY=$(safety check -r "${REPO_ROOT}/apps/api/requirements.txt" --json 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo 0)
    [[ "$SAFETY" -eq 0 ]] \
      && add_result 5 "OWASP dependency check" "pass" "No known CVEs" 0 \
      || add_result 5 "OWASP dependency check" "critical" "${SAFETY} CVEs" "$SAFETY"
  elif command -v pip-audit &>/dev/null; then
    CVE=$(pip-audit -r "${REPO_ROOT}/apps/api/requirements.txt" 2>/dev/null | grep -c "PYSEC\|CVE" || echo 0)
    [[ "$CVE" -eq 0 ]] \
      && add_result 5 "OWASP dependency check" "pass" "No CVEs via pip-audit" 0 \
      || add_result 5 "OWASP dependency check" "critical" "${CVE} CVEs" "$CVE"
  else
    add_result 5 "OWASP dependency check" "skipped" "safety/pip-audit not installed" 0
  fi
fi

# ── Generate report ───────────────────────────────────────────────────
echo ""
echo "=== Generating compliance report ==="
RESULTS_JSON=$(printf "%s," "${RESULTS[@]}" | sed 's/,$//')
cat > "$REPORT_FILE" <<EOF
{
  "report_version": "1.0.0",
  "generated_at": "${TIMESTAMP}",
  "tool": "SafeContext compliance-check.sh",
  "ci_mode": ${CI_MODE},
  "checks": [${RESULTS_JSON}],
  "summary": {
    "total_checks": ${#RESULTS[@]},
    "has_critical": ${HAS_CRITICAL}
  }
}
EOF
echo "Report: ${REPORT_FILE}"

for r in "${RESULTS[@]}"; do
  name=$(echo "$r" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['check_name'])" 2>/dev/null || echo "?")
  sts=$(echo "$r" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['status'])" 2>/dev/null || echo "?")
  echo "  [${sts}] ${name}"
done

if [[ "$CI_MODE" == "true" ]] && [[ "$HAS_CRITICAL" == "true" ]]; then
  echo "CRITICAL findings — failing CI"
  exit 1
fi
echo "Compliance check complete"
