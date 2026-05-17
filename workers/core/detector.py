"""Domain interfaces for PII/secret detection.

Follows SKILL-BACKEND pattern: DetectorInterface + Finding dataclass.
No ML library is imported here — implementations live in workers/ml/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Finding:
    """Represents a single detected sensitive span in a document."""

    detector: str       # e.g. "presidio.EMAIL_ADDRESS"
    rule_id: str        # e.g. "presidio_email_address"
    span_start: int
    span_end: int
    confidence: float   # 0.0 – 1.0
    severity: str       # "low" | "medium" | "high" | "critical"
    explanation: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "detector": self.detector,
            "rule_id": self.rule_id,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "confidence": self.confidence,
            "severity": self.severity,
            "explanation": self.explanation,
        }


class DetectorInterface(ABC):
    """Contract every detector implementation must fulfil."""

    @abstractmethod
    async def detect(self, text: str, policy: dict) -> list[Finding]:
        """Analyse *text* and return findings according to *policy*.

        Args:
            text:   Raw document content to scan.
            policy: Policy dict; may contain 'entities' list and thresholds.

        Returns:
            Ordered list of Finding objects (may be empty).
        """
        ...
