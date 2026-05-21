package safecontext.policy

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

# ---------------------------------------------------------------------------
# Test: IBAN_CODE sobre umbral → no bloquea (severidad high, no critical)
# ---------------------------------------------------------------------------

test_iban_above_threshold_no_block if {
    findings := [{
        "entity_type": "IBAN_CODE",
        "confidence":  0.90,
        "severity":    "high",
    }]
    not should_block(findings)
}

# ---------------------------------------------------------------------------
# Test: MEDICAL_RECORD con confianza alta → bloquea (critical)
# ---------------------------------------------------------------------------

test_medical_record_blocks if {
    findings := [{
        "entity_type": "MEDICAL_RECORD",
        "confidence":  0.90,
        "severity":    "critical",
    }]
    should_block(findings)
}

# ---------------------------------------------------------------------------
# Test: PASSWORD con confianza alta → bloquea (critical)
# ---------------------------------------------------------------------------

test_password_high_confidence_blocks if {
    findings := [{
        "entity_type": "PASSWORD",
        "confidence":  0.97,
        "severity":    "critical",
    }]
    should_block(findings)
}

# ---------------------------------------------------------------------------
# Test: effective_severity con confianza entre 0.50 y 1.0 → usa severity_map
# ---------------------------------------------------------------------------

test_effective_severity_email_medium if {
    finding := {
        "entity_type": "EMAIL_ADDRESS",
        "confidence":  0.80,
        "severity":    "medium",
    }
    effective_severity(finding) == "medium"
}

test_effective_severity_credit_card_high if {
    finding := {
        "entity_type": "CREDIT_CARD",
        "confidence":  0.85,
        "severity":    "high",
    }
    effective_severity(finding) == "high"
}

# ---------------------------------------------------------------------------
# Test: decision con múltiples hallazgos — todos medium, sin bloqueo
# ---------------------------------------------------------------------------

test_decision_all_medium_no_block if {
    findings := [
        {"entity_type": "EMAIL_ADDRESS", "confidence": 0.95, "severity": "medium"},
        {"entity_type": "PHONE_NUMBER",  "confidence": 0.90, "severity": "medium"},
    ]
    result := decision(findings)
    result.allow == true
    result.critical_count == 0
    result.findings_count == 2
}

# ---------------------------------------------------------------------------
# Test: _blocking_count es 0 con hallazgos no críticos
# ---------------------------------------------------------------------------

test_blocking_count_zero_non_critical if {
    findings := [
        {"entity_type": "PHONE_NUMBER", "confidence": 0.90, "severity": "medium"},
    ]
    _blocking_count(findings) == 0
}

# ---------------------------------------------------------------------------
# Test: _review_count correcto con hallazgo bajo umbral
# ---------------------------------------------------------------------------

test_review_count_one_below_threshold if {
    findings := [
        {"entity_type": "PERSON", "confidence": 0.70, "severity": "medium"},
    ]
    _review_count(findings) == 1
}

# ---------------------------------------------------------------------------
# Test: confidence_thresholds contiene todas las entidades clave
# ---------------------------------------------------------------------------

test_confidence_thresholds_has_api_key if {
    confidence_thresholds["API_KEY"] == 0.95
}

test_confidence_thresholds_has_ssn if {
    confidence_thresholds["SSN"] == 0.85
}

# ---------------------------------------------------------------------------
# Test: severity_map contiene todas las entidades clave
# ---------------------------------------------------------------------------

test_severity_map_api_key_is_critical if {
    severity_map["API_KEY"] == "critical"
}

test_severity_map_ip_address_is_low if {
    severity_map["IP_ADDRESS"] == "low"
}

test_severity_map_credit_card_is_high if {
    severity_map["CREDIT_CARD"] == "high"
}
