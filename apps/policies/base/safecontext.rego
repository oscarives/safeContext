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
# Accepts optional waivers to filter out waived findings before evaluation.
# ---------------------------------------------------------------------------

decision(findings) := decision_with_waivers(findings, [])

decision_with_waivers(findings, waivers) := d if {
    active := active_findings_after_waivers(findings, waivers)
    blocking := _blocking_count(active)
    reviewing := _review_count(active)
    d := {
        "allow":                 blocking == 0,
        "requires_human_review": reviewing > 0,
        "policy_version":        policy_version,
        "findings_count":        count(active),
        "waived_count":          count(findings) - count(active),
        "critical_count":        count([f | f := active[_]; f.severity == "critical"]),
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

# ---------------------------------------------------------------------------
# Tenant-aware policy (F6-A3) — per-tenant threshold and severity overrides
#
# Usage: POST /v1/data/safecontext/policy/tenant_decision with input:
#   {
#     "tenant_id": "<uuid>",
#     "findings": [...],
#     "waivers":  [...],
#     "tenant_config": {
#       "confidence_overrides": {"API_KEY": 0.80},
#       "severity_overrides":   {"IP_ADDRESS": "high"},
#       "blocked_entity_types": ["SSN", "CREDIT_CARD"]
#     }
#   }
#
# If tenant_config is absent or empty, behaves identically to decision().
# ---------------------------------------------------------------------------

# Resolve effective confidence threshold for a given entity type,
# using tenant overrides if present, otherwise base thresholds.
_tenant_threshold(entity_type, tenant_config) := t if {
    t := tenant_config.confidence_overrides[entity_type]
} else := t if {
    t := confidence_thresholds[entity_type]
}

# Resolve effective severity for a given entity type,
# using tenant overrides if present, otherwise base severity_map.
_tenant_severity(entity_type, tenant_config) := s if {
    s := tenant_config.severity_overrides[entity_type]
} else := s if {
    s := severity_map[entity_type]
}

# Tenant-specific should_block: also blocks entity types in blocked_entity_types list
_tenant_should_block(finding, tenant_config) if {
    finding.entity_type == tenant_config.blocked_entity_types[_]
}

_tenant_should_block(finding, tenant_config) if {
    sev := _tenant_severity(finding.entity_type, tenant_config)
    sev == "critical"
    threshold := _tenant_threshold(finding.entity_type, tenant_config)
    finding.confidence >= threshold
}

# Tenant-specific review check
_tenant_requires_review(finding, tenant_config) if {
    threshold := _tenant_threshold(finding.entity_type, tenant_config)
    finding.confidence < threshold
}

_tenant_requires_review(finding, tenant_config) if {
    sev := _tenant_severity(finding.entity_type, tenant_config)
    sev == "critical"
}

# Tenant-aware decision — main entry point for multi-tenant evaluation
tenant_decision(findings, waivers, tenant_config) := d if {
    active := active_findings_after_waivers(findings, waivers)
    blocking := count([f |
        f := active[_]
        _tenant_should_block(f, tenant_config)
    ])
    reviewing := count([f |
        f := active[_]
        _tenant_requires_review(f, tenant_config)
    ])
    d := {
        "allow":                 blocking == 0,
        "requires_human_review": reviewing > 0,
        "policy_version":        policy_version,
        "findings_count":        count(active),
        "waived_count":          count(findings) - count(active),
        "critical_count":        count([f |
            f := active[_]
            sev := _tenant_severity(f.entity_type, tenant_config)
            sev == "critical"
        ]),
    }
}

# Backward compat: tenant_decision with empty config falls back to base behavior
tenant_decision_default(findings, waivers) := tenant_decision(findings, waivers, {
    "confidence_overrides": {},
    "severity_overrides": {},
    "blocked_entity_types": [],
})
