package safecontext.policy

import rego.v1

# Versión de la política — debe coincidir con metadata.json
policy_version := "1.0.0"

# ---------------------------------------------------------------------------
# Mapas de datos: umbrales de confianza y severidades base por clase de entidad
# ---------------------------------------------------------------------------

confidence_thresholds := {
    "EMAIL_ADDRESS":  0.85,
    "PHONE_NUMBER":   0.80,
    "PERSON":         0.90,  # higher threshold — spaCy NER has false positives on common words
    "API_KEY":        0.95,
    "PASSWORD":       0.95,
    "CREDIT_CARD":    0.90,
    "SSN":            0.85,
    "IBAN_CODE":      0.85,
    "IP_ADDRESS":     0.75,
    "MEDICAL_RECORD": 0.85,
}

severity_map := {
    "EMAIL_ADDRESS":  "medium",
    "PHONE_NUMBER":   "medium",
    "PERSON":         "medium",
    "API_KEY":        "critical",
    "PASSWORD":       "critical",
    "CREDIT_CARD":    "high",
    "SSN":            "critical",
    "IBAN_CODE":      "high",
    "IP_ADDRESS":     "low",
    "MEDICAL_RECORD": "critical",
}

# ---------------------------------------------------------------------------
# requires_review: hallazgo individual requiere revisión humana
# ---------------------------------------------------------------------------

requires_review(finding) if {
    threshold := confidence_thresholds[finding.entity_type]
    finding.confidence < threshold
}

requires_review(finding) if {
    finding.severity == "critical"
}

# ---------------------------------------------------------------------------
# effective_severity
# ---------------------------------------------------------------------------

effective_severity(finding) := "low" if {
    finding.confidence < 0.50
}

effective_severity(finding) := base if {
    finding.confidence >= 0.50
    base := severity_map[finding.entity_type]
}

# ---------------------------------------------------------------------------
# should_block: bloquear si hay hallazgo crítico con confianza >= umbral
# ---------------------------------------------------------------------------

should_block(findings) if {
    some f in findings
    f.severity == "critical"
    threshold := confidence_thresholds[f.entity_type]
    f.confidence >= threshold
}

# ---------------------------------------------------------------------------
# _blocking_count: cuenta hallazgos que bloquearían (evita `not` en objetos)
# OPA v1 (import rego.v1): reglas completas con body requieren `if` explícito.
# ---------------------------------------------------------------------------

_blocking_count(findings) := n if {
    n := count([f |
        f := findings[_]
        f.severity == "critical"
        threshold := confidence_thresholds[f.entity_type]
        f.confidence >= threshold
    ])
}

# ---------------------------------------------------------------------------
# _review_count: cuenta hallazgos que requieren revisión
# ---------------------------------------------------------------------------

_review_count(findings) := n if {
    n := count([f | f := findings[_]; requires_review(f)])
}

# ---------------------------------------------------------------------------
# operation_requires_review
# ---------------------------------------------------------------------------

operation_requires_review(findings) if {
    _review_count(findings) > 0
}

# ---------------------------------------------------------------------------
# decision: respuesta consolidada — sin `not` dentro de literales de objeto
# ---------------------------------------------------------------------------

decision(findings) := d if {
    blocking := _blocking_count(findings)
    reviewing := _review_count(findings)
    d := {
        "allow":                 blocking == 0,
        "requires_human_review": reviewing > 0,
        "policy_version":        policy_version,
        "findings_count":        count(findings),
        "critical_count":        count([f | f := findings[_]; f.severity == "critical"]),
    }
}

# ---------------------------------------------------------------------------
# Waiver support — check if a finding is covered by an active waiver
# ---------------------------------------------------------------------------

# should_waive: true if any active waiver's rule_id matches the finding's rule_id
# and the waiver's entity_pattern (regex) matches the finding's matched text.
should_waive(finding, waivers) if {
    some waiver in waivers
    waiver.status == "active"
    waiver.rule_id == finding.rule_id
    regex.match(waiver.entity_pattern, finding.explanation.matched_text)
}

# active_findings_after_waivers: filter out findings covered by an active waiver.
# Returns the subset of findings that are NOT waived.
active_findings_after_waivers(findings, waivers) := [f |
    f := findings[_]
    not should_waive(f, waivers)
]
