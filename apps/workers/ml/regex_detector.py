"""RegexDetector — fast deterministic pre-ML PII/secret detection via regex.

T4: RegexDetector pre-ML layer.

This detector runs *before* Presidio and covers high-confidence secret patterns
that NER models often miss (connection strings, JWT tokens, PEM keys, etc.).
It is intentionally conservative — only patterns with very clear structure and
minimal false-positive rate are included here.

Follows the same DetectorInterface contract as PresidioDetector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from workers.core.detector import DetectorInterface, Finding


@dataclass
class _Rule:
    """Internal representation of a single regex rule."""

    rule_id: str
    pattern: re.Pattern
    severity: str
    confidence: float


class RegexDetector(DetectorInterface):
    """DetectorInterface backed by deterministic regex patterns.

    Designed to run before Presidio as a fast pre-filter for structured secrets
    (connection strings, JWT tokens, PEM private keys, env-var assignments, and
    credit card numbers in non-standard formats).

    All patterns produce Finding objects compatible with _merge_findings() in
    detector_agent, which deduplicates overlapping Presidio findings.
    """

    def __init__(self) -> None:
        self._rules: list[_Rule] = [
            # Database / message-broker connection strings.
            # Matches "protocol://..." URI patterns that always contain credentials.
            _Rule(
                rule_id="regex_connection_string",
                pattern=re.compile(
                    r"(postgresql|mysql|mongodb|redis|amqp|mssql)://[^\s\"']+",
                    re.IGNORECASE,
                ),
                severity="critical",
                confidence=1.0,
            ),
            # JSON Web Tokens: three base64url segments separated by dots.
            # The "eyJ" prefix is the base64url encoding of '{"' — ubiquitous in JWTs.
            _Rule(
                rule_id="regex_jwt_token",
                pattern=re.compile(
                    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
                ),
                severity="high",
                confidence=1.0,
            ),
            # PEM private-key headers (RSA, EC, OPENSSH, or generic PRIVATE KEY).
            _Rule(
                rule_id="regex_pem_private_key",
                pattern=re.compile(
                    r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"
                ),
                severity="critical",
                confidence=1.0,
            ),
            # Environment-variable style assignments for well-known secret variables.
            # e.g. SECRET_KEY=abc123  /  DATABASE_URL=postgres://...
            _Rule(
                rule_id="regex_env_secret_assignment",
                pattern=re.compile(
                    r"(?i)(SECRET_KEY|PRIVATE_KEY|DATABASE_URL|API_SECRET|AUTH_TOKEN)\s*=\s*\S+"
                ),
                severity="high",
                confidence=0.95,
            ),
            # UUID-valued secret assignments — e.g. api_key = a1b2c3d4-...
            _Rule(
                rule_id="regex_uuid_secret_assignment",
                pattern=re.compile(
                    r"(?i)(secret|api_key|token|password)\s*=\s*"
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                ),
                severity="high",
                confidence=0.9,
            ),
            # Credit card numbers in non-standard delimited formats (dots, dashes, spaces).
            # Presidio covers the standard run-together format; this catches the rest.
            _Rule(
                rule_id="regex_credit_card_nonstandard",
                pattern=re.compile(
                    r"\b(?:\d{4}[.\- ]\d{4}[.\- ]\d{4}[.\- ]\d{4})\b"
                ),
                severity="high",
                confidence=0.85,
            ),
        ]

    async def detect(self, text: str, policy: dict) -> list[Finding]:
        """Scan *text* for deterministic secret patterns.

        Args:
            text:   Raw document content to scan.
            policy: Policy dict (currently unused by regex rules; reserved for
                    future per-rule enable/disable flags).

        Returns:
            List of Finding objects sorted ascending by span_start. Empty list
            when no patterns match.
        """
        findings: list[Finding] = []

        for rule in self._rules:
            for match in rule.pattern.finditer(text):
                matched = match.group()
                findings.append(
                    Finding(
                        detector=f"regex.{rule.rule_id.upper()}",
                        rule_id=rule.rule_id,
                        span_start=match.start(),
                        span_end=match.end(),
                        confidence=rule.confidence,
                        severity=rule.severity,
                        explanation={
                            "pattern": rule.rule_id,
                            "matched_preview": (
                                matched[:30] + "..." if len(matched) > 30 else matched
                            ),
                        },
                    )
                )

        return sorted(findings, key=lambda f: f.span_start)
