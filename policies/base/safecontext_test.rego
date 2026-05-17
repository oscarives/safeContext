package safecontext.policy_test

import future.keywords.if

# ---------------------------------------------------------------------------
# Test: hallazgo crítico con confianza alta → should_block
# ---------------------------------------------------------------------------

test_should_block_critical_high_confidence if {
    findings := [{
        "entity_type": "API_KEY",
        "confidence":  0.97,
        "severity":    "critical",
    }]
    should_block(findings)
}

# ---------------------------------------------------------------------------
# Test: hallazgo crítico con confianza baja → no bloquea pero requiere revisión
# ---------------------------------------------------------------------------

test_no_block_critical_low_confidence if {
    findings := [{
        "entity_type": "API_KEY",
        "confidence":  0.70,
        "severity":    "critical",
    }]
    not should_block(findings)
    operation_requires_review(findings)
}

# ---------------------------------------------------------------------------
# Test: hallazgo no crítico sobre umbral → no bloquea, no requiere revisión
# ---------------------------------------------------------------------------

test_allow_non_critical_above_threshold if {
    findings := [{
        "entity_type": "EMAIL_ADDRESS",
        "confidence":  0.92,
        "severity":    "medium",
    }]
    not should_block(findings)
    not operation_requires_review(findings)
}

# ---------------------------------------------------------------------------
# Test: hallazgo bajo umbral → requiere revisión
# ---------------------------------------------------------------------------

test_requires_review_below_threshold if {
    findings := [{
        "entity_type": "EMAIL_ADDRESS",
        "confidence":  0.70,
        "severity":    "medium",
    }]
    operation_requires_review(findings)
}

# ---------------------------------------------------------------------------
# Test: sin hallazgos → allow, no review
# ---------------------------------------------------------------------------

test_empty_findings_allow if {
    decision([]).allow == true
    decision([]).requires_human_review == false
}

# ---------------------------------------------------------------------------
# Test: policy_version tiene formato semver (X.Y.Z)
# ---------------------------------------------------------------------------

test_policy_version_format if {
    regex.match(`^\d+\.\d+\.\d+$`, policy_version)
}

# ---------------------------------------------------------------------------
# Test: severidad efectiva con confianza muy baja → "low"
# ---------------------------------------------------------------------------

test_effective_severity_low_confidence if {
    finding := {
        "entity_type": "API_KEY",
        "confidence":  0.30,
        "severity":    "critical",
    }
    effective_severity(finding) == "low"
}

# ---------------------------------------------------------------------------
# Test: severidad efectiva con confianza alta → severidad base del mapa
# ---------------------------------------------------------------------------

test_effective_severity_high_confidence if {
    finding := {
        "entity_type": "API_KEY",
        "confidence":  0.97,
        "severity":    "critical",
    }
    effective_severity(finding) == "critical"
}

# ---------------------------------------------------------------------------
# Test: decisión consolidada con múltiples hallazgos (EMAIL medium + API_KEY critical)
# ---------------------------------------------------------------------------

test_decision_mixed_findings if {
    findings := [
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.90, "severity": "medium"},
        {"entity_type": "API_KEY",       "confidence": 0.98, "severity": "critical"},
    ]
    result := decision(findings)
    result.allow == false
    result.critical_count == 1
    result.findings_count == 2
}

# ---------------------------------------------------------------------------
# Test: requires_review es true para hallazgo crítico (por severidad)
# ---------------------------------------------------------------------------

test_requires_review_critical_severity if {
    finding := {
        "entity_type": "SSN",
        "confidence":  0.99,
        "severity":    "critical",
    }
    requires_review(finding)
}

# ---------------------------------------------------------------------------
# Test: SSN con alta confianza bloquea la operación
# ---------------------------------------------------------------------------

test_should_block_ssn_high_confidence if {
    findings := [{
        "entity_type": "SSN",
        "confidence":  0.90,
        "severity":    "critical",
    }]
    should_block(findings)
}

# ---------------------------------------------------------------------------
# Test: IP_ADDRESS sobre umbral → no bloquea, no requiere revisión
# ---------------------------------------------------------------------------

test_ip_address_above_threshold_no_block if {
    findings := [{
        "entity_type": "IP_ADDRESS",
        "confidence":  0.80,
        "severity":    "low",
    }]
    not should_block(findings)
    not operation_requires_review(findings)
}

# ---------------------------------------------------------------------------
# Test: CREDIT_CARD sobre umbral → no bloquea (no es crítico)
# ---------------------------------------------------------------------------

test_credit_card_above_threshold_no_block if {
    findings := [{
        "entity_type": "CREDIT_CARD",
        "confidence":  0.95,
        "severity":    "high",
    }]
    not should_block(findings)
}

# ---------------------------------------------------------------------------
# Test: decision.policy_version coincide con la constante policy_version
# ---------------------------------------------------------------------------

test_decision_contains_policy_version if {
    result := decision([])
    result.policy_version == policy_version
}
