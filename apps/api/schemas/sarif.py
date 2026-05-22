"""SARIF 2.1.0 output schemas for SafeContext audit export.

Implements the Static Analysis Results Interchange Format (SARIF) 2.1.0
subset needed to represent SafeContext findings as tool results that can
be consumed by GitHub Advanced Security, VS Code, and other SARIF viewers.

Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SarifRegion(BaseModel):
    startLine: int = 1
    startColumn: int
    endColumn: int


class SarifArtifactLocation(BaseModel):
    uri: str = "document"


class SarifPhysicalLocation(BaseModel):
    artifactLocation: SarifArtifactLocation = Field(default_factory=SarifArtifactLocation)
    region: SarifRegion


class SarifLocation(BaseModel):
    physicalLocation: SarifPhysicalLocation


class SarifResult(BaseModel):
    ruleId: str
    level: str  # "error" | "warning" | "note" | "none"
    message: dict
    locations: list[SarifLocation]
    properties: dict = Field(default_factory=dict)


class SarifDriver(BaseModel):
    name: str = "SafeContext"
    version: str = "1.0.0"


class SarifTool(BaseModel):
    driver: SarifDriver = Field(default_factory=SarifDriver)


class SarifRun(BaseModel):
    tool: SarifTool = Field(default_factory=SarifTool)
    results: list[SarifResult]
    properties: dict = Field(default_factory=dict)


class SarifOutput(BaseModel):
    version: str = "2.1.0"
    schema_: str = Field(
        "https://json.schemastore.org/sarif-2.1.0.json",
        alias="$schema",
    )
    runs: list[SarifRun]

    model_config = {"populate_by_name": True}


def audit_to_sarif(audit: "AuditExportResponse") -> SarifOutput:  # type: ignore[name-defined]
    """Convert an AuditExportResponse to a SARIF 2.1.0 output document.

    Severity mapping (SafeContext → SARIF level):
      critical → error
      high     → warning
      medium   → note
      low      → none
    """
    severity_map = {
        "critical": "error",
        "high": "warning",
        "medium": "note",
        "low": "none",
    }
    results = []
    for f in audit.findings:
        results.append(
            SarifResult(
                ruleId=f.detector,
                level=severity_map.get(f.severity, "note"),
                message={"text": f.rule_id},
                locations=[
                    SarifLocation(
                        physicalLocation=SarifPhysicalLocation(
                            region=SarifRegion(
                                startColumn=f.span_start,
                                endColumn=f.span_end,
                            ),
                        )
                    )
                ],
                properties={
                    "confidence": f.confidence,
                    "explanation": f.explanation,
                },
            )
        )
    return SarifOutput(
        runs=[
            SarifRun(
                results=results,
                properties={
                    "safecontext": {
                        "hmac_signature": audit.hmac_signature,
                        "trace_id": str(audit.trace_id),
                    }
                },
            )
        ]
    )
