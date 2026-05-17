"""PresidioDetector — DetectorInterface implementation using Microsoft Presidio.

ADR-010: Presidio + spaCy en_core_web_lg as the default PII detection engine.
The model is baked into the Docker image at build time (not downloaded at runtime).
"""
from __future__ import annotations

import logging
from typing import Any

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer import Pattern

from workers.core.detector import DetectorInterface, Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity map — mirrors safecontext.rego severity_map for consistency
# ---------------------------------------------------------------------------

_SEVERITY: dict[str, str] = {
    "EMAIL_ADDRESS": "medium",
    "PHONE_NUMBER": "medium",
    "PERSON": "medium",
    "API_KEY": "critical",
    "PASSWORD": "critical",
    "CREDIT_CARD": "high",
    "SSN": "critical",
    "IBAN_CODE": "high",
    "IP_ADDRESS": "low",
    "MEDICAL_RECORD": "critical",
}

# Default entity list when policy doesn't specify one
_DEFAULT_ENTITIES: list[str] = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "PERSON",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "SSN",
    "API_KEY",
]

# ---------------------------------------------------------------------------
# Custom API_KEY recognizer
# Covers common API key formats: sk-*, ghp_*, hf_*, Bearer JWT, AWS keys,
# Slack tokens (xoxb-), and generic high-entropy secret patterns.
# ---------------------------------------------------------------------------

_API_KEY_PATTERNS: list[Pattern] = [
    # OpenAI / Anthropic style: sk-<alphanum>
    Pattern(
        name="openai_sk_key",
        regex=r"\bsk-[A-Za-z0-9]{20,}\b",
        score=0.9,
    ),
    # OpenAI project key: sk-proj-<alphanum>
    Pattern(
        name="openai_proj_key",
        regex=r"\bsk-proj-[A-Za-z0-9\-_]{20,}\b",
        score=0.9,
    ),
    # Anthropic: sk-ant-<alphanum>
    Pattern(
        name="anthropic_key",
        regex=r"\bsk-ant-[A-Za-z0-9\-_]{10,}\b",
        score=0.9,
    ),
    # GitHub PAT: ghp_<alphanum>
    Pattern(
        name="github_pat",
        regex=r"\bghp_[A-Za-z0-9]{36,}\b",
        score=0.9,
    ),
    # HuggingFace token: hf_<alphanum>
    Pattern(
        name="huggingface_token",
        regex=r"\bhf_[A-Za-z0-9]{20,}\b",
        score=0.85,
    ),
    # Slack token: xoxb-<digits>-<digits>-<alphanum>
    Pattern(
        name="slack_token",
        regex=r"\bxoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+\b",
        score=0.9,
    ),
    # Stripe live key: sk_live_<alphanum>
    Pattern(
        name="stripe_live_key",
        regex=r"\bsk_live_[A-Za-z0-9]{24,}\b",
        score=0.95,
    ),
    # AWS access key ID: AKIA<alphanum>
    Pattern(
        name="aws_access_key_id",
        regex=r"\bAKIA[A-Z0-9]{16}\b",
        score=0.95,
    ),
    # Bearer token (JWT or opaque): "Bearer <token>"
    Pattern(
        name="bearer_token",
        regex=r"(?i)\bBearer\s+[A-Za-z0-9\-_\.]{20,}\b",
        score=0.8,
    ),
    # UUID-like secret (client_secret, api_key assignment patterns)
    Pattern(
        name="uuid_secret",
        regex=r"(?i)(?:secret|api.?key|token)\s*[=:]\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        score=0.85,
    ),
]


def _build_api_key_recognizer() -> PatternRecognizer:
    """Build a custom PatternRecognizer for API keys / secrets."""
    return PatternRecognizer(
        supported_entity="API_KEY",
        patterns=_API_KEY_PATTERNS,
        supported_language="en",
        name="ApiKeyRecognizer",
    )


def _build_analyzer() -> AnalyzerEngine:
    """Construct and return a shared AnalyzerEngine backed by spaCy."""
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    # Register custom API_KEY recognizer
    analyzer.registry.add_recognizer(_build_api_key_recognizer())
    return analyzer


class PresidioDetector(DetectorInterface):
    """DetectorInterface backed by Microsoft Presidio + spaCy.

    The AnalyzerEngine is instantiated lazily on first use and shared across
    calls (thread-safe after initialisation per Presidio docs).
    """

    _analyzer: AnalyzerEngine | None = None

    def _get_analyzer(self) -> AnalyzerEngine:
        if PresidioDetector._analyzer is None:
            logger.info("presidio_detector.init loading spaCy model")
            PresidioDetector._analyzer = _build_analyzer()
            logger.info("presidio_detector.init ready")
        return PresidioDetector._analyzer

    async def detect(self, text: str, policy: dict) -> list[Finding]:
        """Analyse *text* and return a list of Finding objects.

        Args:
            text:   Raw text to scan.
            policy: Dict that may contain:
                    - 'entities': list[str]  — overrides default entity list
                    - 'score_threshold': float — minimum confidence (default 0.5)
        """
        entities: list[str] = policy.get("entities", _DEFAULT_ENTITIES)
        score_threshold: float = float(policy.get("score_threshold", 0.5))

        analyzer = self._get_analyzer()

        try:
            results: list[RecognizerResult] = analyzer.analyze(
                text=text,
                entities=entities,
                language="en",
                score_threshold=score_threshold,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("presidio_detector.analyze_error error=%s", exc)
            return []

        findings: list[Finding] = []
        for r in results:
            entity_type: str = r.entity_type
            severity: str = _SEVERITY.get(entity_type, "medium")
            finding = Finding(
                detector=f"presidio.{entity_type}",
                rule_id=f"presidio_{entity_type.lower()}",
                span_start=r.start,
                span_end=r.end,
                confidence=round(float(r.score), 4),
                severity=severity,
                explanation={
                    "entity_type": entity_type,
                    "recognition_metadata": r.recognition_metadata or {},
                    "analysis_explanation": (
                        str(r.analysis_explanation)
                        if r.analysis_explanation
                        else None
                    ),
                },
            )
            findings.append(finding)

        logger.debug(
            "presidio_detector.detect findings=%d text_len=%d",
            len(findings),
            len(text),
        )
        return findings
