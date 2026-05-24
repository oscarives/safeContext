"""Compliance report schemas for SOC 2, ISO 27001, GDPR Art. 30.

Each framework defines a set of controls mapped to SafeContext evidence.
Reports are populated with real system data (operation counts, audit trail
status, encryption config, retention policy, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


FrameworkType = Literal["soc2", "iso27001", "gdpr"]


class ControlEvidence(BaseModel):
    """A single compliance control with mapped evidence."""

    control_id: str
    control_name: str
    description: str
    status: Literal["met", "partial", "not_met", "not_applicable"]
    evidence: list[str]
    notes: str | None = None


class ComplianceReport(BaseModel):
    """Compliance report for a specific framework."""

    report_id: str
    framework: FrameworkType
    framework_version: str
    generated_at: datetime
    tenant_id: str
    period_start: datetime
    period_end: datetime
    controls: list[ControlEvidence]
    summary: ComplianceSummary
    metadata: dict[str, Any] = {}


class ComplianceSummary(BaseModel):
    """Aggregate summary of control statuses."""

    total_controls: int
    met: int
    partial: int
    not_met: int
    not_applicable: int
    compliance_score: float  # 0.0 - 1.0


# ── Framework templates ───────────────────────────────────────────────────


SOC2_CONTROLS = [
    {
        "control_id": "CC6.1",
        "control_name": "Logical and Physical Access Controls",
        "description": "The entity implements logical access security software, infrastructure, and architectures over protected information assets.",
        "evidence_keys": ["auth_oidc", "mfa_enforced", "rbac_roles"],
    },
    {
        "control_id": "CC6.6",
        "control_name": "System Boundary Protection",
        "description": "The entity implements logical access security measures to protect against threats from sources outside its system boundaries.",
        "evidence_keys": ["rate_limiting", "input_validation", "opa_policies"],
    },
    {
        "control_id": "CC7.2",
        "control_name": "Security Event Monitoring",
        "description": "The entity monitors system components for anomalies indicative of malicious acts and natural disasters.",
        "evidence_keys": ["structured_logging", "audit_trail", "siem_integration"],
    },
    {
        "control_id": "CC8.1",
        "control_name": "Change Management",
        "description": "The entity authorizes, designs, develops, configures, documents, tests, approves, and implements changes.",
        "evidence_keys": ["ci_pipeline", "sbom_signed", "policy_versioning"],
    },
    {
        "control_id": "CC9.1",
        "control_name": "Risk Mitigation",
        "description": "The entity identifies, selects, and develops risk mitigation activities.",
        "evidence_keys": ["pii_detection", "sanitization", "segregation_of_duties"],
    },
]


ISO27001_CONTROLS = [
    {
        "control_id": "A.8.2",
        "control_name": "Information Classification",
        "description": "Information shall be classified in terms of legal requirements, value, criticality and sensitivity.",
        "evidence_keys": ["severity_classification", "finding_categories", "opa_policies"],
    },
    {
        "control_id": "A.8.11",
        "control_name": "Data Masking",
        "description": "Data masking shall be applied in accordance with the organization's topic-specific policy on access control.",
        "evidence_keys": ["sanitization", "redaction_types", "pii_detection"],
    },
    {
        "control_id": "A.8.15",
        "control_name": "Logging",
        "description": "Logs that record activities, exceptions, faults and other relevant events shall be produced, stored, protected and analysed.",
        "evidence_keys": ["structured_logging", "audit_trail", "worm_retention"],
    },
    {
        "control_id": "A.8.24",
        "control_name": "Use of Cryptography",
        "description": "Rules for the effective use of cryptography shall be defined and implemented.",
        "evidence_keys": ["hmac_signing", "vault_transit", "tsa_timestamps", "chain_hash"],
    },
    {
        "control_id": "A.5.34",
        "control_name": "Privacy and Protection of PII",
        "description": "The organization shall identify and meet the requirements regarding the preservation of privacy and protection of PII.",
        "evidence_keys": ["pii_detection", "gdpr_retention", "deletion_certificates"],
    },
]


GDPR_CONTROLS = [
    {
        "control_id": "Art.5.1.b",
        "control_name": "Purpose Limitation",
        "description": "Personal data collected for specified, explicit and legitimate purposes.",
        "evidence_keys": ["trace_id_tracking", "actor_id_attribution", "policy_versioning"],
    },
    {
        "control_id": "Art.5.1.e",
        "control_name": "Storage Limitation",
        "description": "Personal data kept in a form which permits identification for no longer than necessary.",
        "evidence_keys": ["retention_policy", "gdpr_retention", "deletion_certificates"],
    },
    {
        "control_id": "Art.25",
        "control_name": "Data Protection by Design",
        "description": "Implementation of appropriate technical and organisational measures for data protection.",
        "evidence_keys": ["pii_detection", "sanitization", "opa_policies", "encryption"],
    },
    {
        "control_id": "Art.30",
        "control_name": "Records of Processing Activities",
        "description": "Each controller shall maintain a record of processing activities.",
        "evidence_keys": ["audit_trail", "operation_records", "tenant_isolation"],
    },
    {
        "control_id": "Art.32",
        "control_name": "Security of Processing",
        "description": "Implement appropriate technical and organisational measures to ensure security.",
        "evidence_keys": ["auth_oidc", "mfa_enforced", "vault_transit", "rls_isolation"],
    },
]


FRAMEWORK_TEMPLATES: dict[str, list[dict]] = {
    "soc2": SOC2_CONTROLS,
    "iso27001": ISO27001_CONTROLS,
    "gdpr": GDPR_CONTROLS,
}

FRAMEWORK_VERSIONS: dict[str, str] = {
    "soc2": "SOC 2 Type II (2017)",
    "iso27001": "ISO/IEC 27001:2022",
    "gdpr": "GDPR (EU 2016/679)",
}
