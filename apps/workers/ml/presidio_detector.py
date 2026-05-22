"""PresidioDetector — DetectorInterface implementation using Microsoft Presidio.

ADR-010: Presidio + spaCy en_core_web_lg as the default PII detection engine.
The model is baked into the Docker image at build time (not downloaded at runtime).

E5.3: model_loader guarantees resolution from local paths (image-baked or
volume-mounted) without internet access at runtime.
"""

from __future__ import annotations

import logging
import threading

# Email domains that are clearly test/example data and should not be flagged as PII.
# These are standard RFC 2606 / IANA reserved domains plus common dev placeholders.
_EXEMPT_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "test.com", "test.local", "test.org", "test.net",
    "example.com", "example.org", "example.net",
    "localhost", "local", "invalid",
    "testmail.com", "mailtest.com",
})

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, RecognizerResult
from presidio_analyzer import Pattern

from workers.core.detector import DetectorInterface, Finding
from workers.ml.model_loader import load_spacy_nlp, verify_models_available

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
    """Construct and return a shared AnalyzerEngine backed by spaCy.

    Uses model_loader to resolve the spaCy model from local paths (image-baked
    or volume-mounted) — never downloads at runtime (ADR-010, E5.3).
    """
    # Log availability before loading (warns on misconfigured air-gapped setups)
    availability = verify_models_available()
    for model, available in availability.items():
        if not available:
            logger.warning("presidio_detector.model_unavailable model=%s", model)

    # Load spaCy NLP from local path via model_loader
    nlp = load_spacy_nlp()

    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    nlp_engine = SpacyNlpEngine(
        models=[{"lang_code": "en", "model_name": "en_core_web_lg"}]
    )
    # Inject the already-loaded nlp object to avoid a second load
    nlp_engine.nlp = {"en": nlp}

    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    # Register custom API_KEY recognizer
    analyzer.registry.add_recognizer(_build_api_key_recognizer())
    return analyzer


_analyzer_lock = threading.Lock()


class PresidioDetector(DetectorInterface):
    """DetectorInterface backed by Microsoft Presidio + spaCy.

    The AnalyzerEngine is instantiated lazily on first use and shared across
    calls via a class-level singleton.  Double-checked locking with a
    threading.Lock prevents duplicate model loads when two Dramatiq worker
    threads race on the first call (model load takes ~10 s and several GB RAM).
    """

    _analyzer: AnalyzerEngine | None = None

    def _get_analyzer(self) -> AnalyzerEngine:
        if PresidioDetector._analyzer is None:
            with _analyzer_lock:
                # Second check inside the lock (double-checked locking pattern)
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
            matched_text: str = text[r.start:r.end]

            # Skip already-redacted spans — document was previously sanitized
            if "[REDACTED]" in matched_text:
                continue

            # Skip email addresses from known test/example domains (false positives
            # produced when test data or previously-sanitized content is re-scanned)
            if entity_type == "EMAIL_ADDRESS" and "@" in matched_text:
                domain = matched_text.split("@")[-1].strip().lower()
                if domain in _EXEMPT_EMAIL_DOMAINS:
                    logger.debug(
                        "presidio_detector.exempt_email",
                        domain=domain,
                        span=f"{r.start}:{r.end}",
                    )
                    continue

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
                        str(r.analysis_explanation) if r.analysis_explanation else None
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
