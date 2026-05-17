package safecontext.policy

import future.keywords.if
import future.keywords.in

# Versión de la política — debe coincidir con metadata.json
policy_version := "1.0.0"

# ---------------------------------------------------------------------------
# Mapas de datos: umbrales de confianza y severidades base por clase de entidad
# ---------------------------------------------------------------------------

confidence_thresholds := {
    "EMAIL_ADDRESS":  0.85,
    "PHONE_NUMBER":   0.80,
    "PERSON":         0.85,
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
# requires_review: determina si un hallazgo individual requiere revisión humana
# Regla: confianza < umbral de la clase  OR  severidad == "critical"
# ---------------------------------------------------------------------------

requires_review(finding) if {
    threshold := confidence_thresholds[finding.entity_type]
    finding.confidence < threshold
}

requires_review(finding) if {
    finding.severity == "critical"
}

# ---------------------------------------------------------------------------
# effective_severity: severidad efectiva de un hallazgo
# Si confianza < 0.50 → "low" (independientemente de la clase)
# Si confianza >= 0.50 → severidad base del mapa
# ---------------------------------------------------------------------------

effective_severity(finding) := "low" if {
    finding.confidence < 0.50
}

effective_severity(finding) := base if {
    finding.confidence >= 0.50
    base := severity_map[finding.entity_type]
}

# ---------------------------------------------------------------------------
# should_block: bloquear si existe algún hallazgo crítico con confianza >= umbral
# ---------------------------------------------------------------------------

should_block(findings) if {
    some f in findings
    f.severity == "critical"
    threshold := confidence_thresholds[f.entity_type]
    f.confidence >= threshold
}

# ---------------------------------------------------------------------------
# operation_requires_review: la operación requiere revisión si algún hallazgo lo requiere
# ---------------------------------------------------------------------------

operation_requires_review(findings) if {
    some f in findings
    requires_review(f)
}

# ---------------------------------------------------------------------------
# decision: respuesta consolidada para una operación
# ---------------------------------------------------------------------------

decision(findings) := {
    "allow":                not should_block(findings),
    "requires_human_review": operation_requires_review(findings),
    "policy_version":       policy_version,
    "findings_count":       count(findings),
    "critical_count":       count([f | f := findings[_]; f.severity == "critical"]),
}
