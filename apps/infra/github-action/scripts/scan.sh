#!/usr/bin/env bash
# SafeContext scan script — invokes safecontext.scan and evaluates results.
# Exit 0 = pass (no findings above threshold)
# Exit 1 = block (findings at or above fail-on-severity)
set -euo pipefail

SEVERITY_ORDER=("low" "medium" "high" "critical")

severity_rank() {
  local sev="$1"
  for i in "${!SEVERITY_ORDER[@]}"; do
    [[ "${SEVERITY_ORDER[$i]}" == "$sev" ]] && echo "$i" && return
  done
  echo "0"
}

# ── Collect document content ──────────────────────────────────────────────────
if [[ -f "$SC_DOCUMENT_PATH" ]]; then
  DOCUMENT=$(cat "$SC_DOCUMENT_PATH")
elif [[ -d "$SC_DOCUMENT_PATH" ]]; then
  # Concatenate all text files in directory (limit to 500KB)
  DOCUMENT=$(find "$SC_DOCUMENT_PATH" \
    -type f \( -name "*.py" -o -name "*.ts" -o -name "*.js" -o -name "*.md" \
               -o -name "*.txt" -o -name "*.yaml" -o -name "*.yml" \) \
    -not -path "*/node_modules/*" -not -path "*/.git/*" \
    | head -50 \
    | xargs cat 2>/dev/null \
    | head -c 512000)
else
  echo "::error::SC_DOCUMENT_PATH not found: $SC_DOCUMENT_PATH"
  exit 1
fi

if [[ -z "$DOCUMENT" ]]; then
  echo "::warning::No document content found at $SC_DOCUMENT_PATH — skipping scan"
  echo "result=pass" >> "$GITHUB_OUTPUT"
  echo "findings_count=0" >> "$GITHUB_OUTPUT"
  exit 0
fi

# ── Call safecontext.scan ─────────────────────────────────────────────────────
PAYLOAD=$(jq -nc \
  --arg doc "$DOCUMENT" \
  --arg policy "$SC_POLICY" \
  '{"document": $doc, "policy_name": $policy}')

HTTP_RESPONSE=$(curl --silent --show-error --fail-with-body \
  --max-time 30 \
  -X POST "${SC_API_URL}/v1/mcp/tools/safecontext.scan" \
  -H "Authorization: Bearer ${SC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -w "\n__HTTP_STATUS__%{http_code}" 2>&1) || {
    echo "::error::SafeContext API call failed: $HTTP_RESPONSE"
    exit 1
  }

HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')
HTTP_STATUS=$(echo "$HTTP_RESPONSE" | tail -1 | sed 's/__HTTP_STATUS__//')

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "::error::SafeContext returned HTTP $HTTP_STATUS"
  exit 1
fi

# ── Parse response ────────────────────────────────────────────────────────────
TRACE_ID=$(echo "$HTTP_BODY" | jq -r '.trace_id // .output.trace_id // "unknown"')
FINDINGS=$(echo "$HTTP_BODY" | jq -r '.output.findings // []')
FINDINGS_COUNT=$(echo "$FINDINGS" | jq 'length')
REQUIRES_REVIEW=$(echo "$HTTP_BODY" | jq -r '.output.requires_human_review // false')

echo "trace_id=${TRACE_ID}" >> "$GITHUB_OUTPUT"
echo "findings_count=${FINDINGS_COUNT}" >> "$GITHUB_OUTPUT"

# ── Determine pass/block ──────────────────────────────────────────────────────
FAIL_RANK=$(severity_rank "$SC_FAIL_ON")
BLOCK=false

while IFS= read -r finding; do
  SEV=$(echo "$finding" | jq -r '.severity // "low"')
  SEV_RANK=$(severity_rank "$SEV")
  if (( SEV_RANK >= FAIL_RANK )); then
    BLOCK=true
    break
  fi
done < <(echo "$FINDINGS" | jq -c '.[]')

# ── Generate Markdown report ──────────────────────────────────────────────────
REPORT_FILE="/tmp/safecontext-report.md"
{
  if [[ "$BLOCK" == "true" ]]; then
    echo "## ⛔ SafeContext: Security Gate — BLOCKED"
  else
    echo "## ✅ SafeContext: Security Gate — PASSED"
  fi
  echo ""
  echo "| Field | Value |"
  echo "|---|---|"
  echo "| Trace ID | \`${TRACE_ID}\` |"
  echo "| Policy | \`${SC_POLICY}\` |"
  echo "| Findings | ${FINDINGS_COUNT} |"
  echo "| Requires human review | ${REQUIRES_REVIEW} |"
  echo "| Threshold | ${SC_FAIL_ON}+ |"
  echo ""

  if (( FINDINGS_COUNT > 0 )); then
    echo "### Findings"
    echo ""
    echo "| Detector | Rule | Severity | Confidence | Span |"
    echo "|---|---|---|---|---|"
    while IFS= read -r f; do
      DET=$(echo "$f" | jq -r '.detector')
      RULE=$(echo "$f" | jq -r '.rule_id')
      SEV=$(echo "$f" | jq -r '.severity')
      CONF=$(echo "$f" | jq -r '.confidence')
      START=$(echo "$f" | jq -r '.span_start')
      END=$(echo "$f" | jq -r '.span_end')
      echo "| \`${DET}\` | \`${RULE}\` | **${SEV}** | ${CONF} | [${START}:${END}] |"
    done < <(echo "$FINDINGS" | jq -c '.[]')
  fi

  echo ""
  echo "_Powered by [SafeContext](https://github.com/safecontext/safecontext) · Trace: \`${TRACE_ID}\`_"
} > "$REPORT_FILE"

# ── Output result ─────────────────────────────────────────────────────────────
if [[ "$BLOCK" == "true" ]]; then
  echo "result=block" >> "$GITHUB_OUTPUT"
  echo "::error::SafeContext blocked: ${FINDINGS_COUNT} finding(s) at or above '${SC_FAIL_ON}' severity. Trace: ${TRACE_ID}"
  cat "$REPORT_FILE"
  exit 1
else
  echo "result=pass" >> "$GITHUB_OUTPUT"
  echo "::notice::SafeContext passed: ${FINDINGS_COUNT} finding(s), none at or above '${SC_FAIL_ON}' severity. Trace: ${TRACE_ID}"
  exit 0
fi
