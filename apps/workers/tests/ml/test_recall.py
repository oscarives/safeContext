"""Recall evaluation tests for SafeContext detectors.

AC E1.5-9: Recall ≥ 0.90 on the labelled corpus for EMAIL_ADDRESS,
           API_KEY, and PERSON entity classes.

F2 gate: PII classes ≥ 0.95, critical secret classes ≥ 0.99.

Methodology:
  - For each sample in corpus.json, run PresidioDetector.detect() and
    RegexDetector.detect() and merge results.
  - A predicted span is a True Positive (TP) for an expected annotation if:
      * entity_type matches (using explanation["entity_type"] for Presidio
        findings, or using f.detector for regex findings), AND
      * IoU (intersection over union) of the spans ≥ 0.5
        (i.e. there is meaningful overlap — exact match not required).
  - Recall = TP / (TP + FN) per class.
  - Each class must achieve recall ≥ the class-specific threshold.

Note: The spaCy model (en_core_web_lg) must be available in the environment.
      In CI the Docker image installs it at build time (ADR-010).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import pytest

# ---------------------------------------------------------------------------
# Thresholds — differentiated by risk category
# ---------------------------------------------------------------------------

# Legacy threshold (kept for backward compat with AC E1.5-9)
RECALL_THRESHOLD: float = 0.90

# PII entities: recall ≥ 0.95 (F2 gate)
PII_RECALL_THRESHOLD: float = 0.95

# Critical secret entities: recall ≥ 0.99 (deterministic regex — should be near-perfect)
SECRET_RECALL_THRESHOLD: float = 0.99

# Entity classes under evaluation — grouped by threshold
PII_ENTITY_CLASSES: list[str] = [
    "EMAIL_ADDRESS",
    "PERSON",
    "SSN",
    "CREDIT_CARD",
    "IBAN_CODE",
    "PHONE_NUMBER",
]

SECRET_ENTITY_CLASSES: list[str] = [
    "API_KEY",
    "REGEX_CONNECTION_STRING",
    "REGEX_JWT_TOKEN",
    "REGEX_PEM_PRIVATE_KEY",
]

# All classes (union — used for the minimum-samples check)
ENTITY_CLASSES: list[str] = PII_ENTITY_CLASSES + SECRET_ENTITY_CLASSES

# Regex-backed entity types (matched via f.detector, not explanation["entity_type"])
_REGEX_ENTITY_TYPES: set[str] = {
    "REGEX_CONNECTION_STRING",
    "REGEX_JWT_TOKEN",
    "REGEX_PEM_PRIVATE_KEY",
    "REGEX_ENV_SECRET_ASSIGNMENT",
    "REGEX_UUID_SECRET_ASSIGNMENT",
    "REGEX_CREDIT_CARD_NONSTANDARD",
}

# Path to corpus relative to this file
_CORPUS_PATH = Path(__file__).parent.parent / "fixtures" / "corpus" / "corpus.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class Annotation(NamedTuple):
    entity_type: str
    span_start: int
    span_end: int


class EvalResult(NamedTuple):
    entity_type: str
    tp: int
    fn: int
    recall: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _span_iou(
    pred_start: int,
    pred_end: int,
    gold_start: int,
    gold_end: int,
) -> float:
    """Compute Intersection-over-Union for two character spans."""
    inter_start = max(pred_start, gold_start)
    inter_end = min(pred_end, gold_end)
    if inter_start >= inter_end:
        return 0.0
    intersection = inter_end - inter_start
    union = (pred_end - pred_start) + (gold_end - gold_start) - intersection
    return intersection / union if union > 0 else 0.0


def _load_corpus() -> list[dict]:
    with open(_CORPUS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["samples"]


def _finding_entity_type(pred) -> str:
    """Extract the canonical entity_type from a Finding.

    Presidio findings store it in explanation["entity_type"].
    RegexDetector findings store the rule name in explanation["pattern"]
    and the detector string is "regex.RULE_ID_UPPER" — extract the
    RULE_ID_UPPER suffix and prefix with "REGEX_".
    """
    # Try Presidio-style first
    presidio_type = pred.explanation.get("entity_type", "")
    if presidio_type:
        return presidio_type

    # Regex-style: detector = "regex.REGEX_CONNECTION_STRING"
    detector: str = pred.detector or ""
    if detector.startswith("regex."):
        return detector[len("regex."):]  # e.g. "REGEX_CONNECTION_STRING"

    return ""


def _predictions_hit(
    predictions: list,  # list[Finding]
    gold: Annotation,
    iou_threshold: float = 0.5,
) -> bool:
    """Return True if any prediction covers *gold* with sufficient IoU."""
    for pred in predictions:
        pred_entity = _finding_entity_type(pred)
        if pred_entity != gold.entity_type:
            continue
        iou = _span_iou(pred.span_start, pred.span_end, gold.span_start, gold.span_end)
        if iou >= iou_threshold:
            return True
    return False


# ---------------------------------------------------------------------------
# Evaluation function (SKILL-ML)
# ---------------------------------------------------------------------------


def evaluate_recall(entity_type: str) -> EvalResult:
    """Run all detectors over all corpus samples and compute recall
    for *entity_type*.
    """
    import asyncio

    # Import here to avoid loading spaCy at collection time
    from workers.ml.presidio_detector import PresidioDetector
    from workers.ml.regex_detector import RegexDetector

    corpus = _load_corpus()
    presidio = PresidioDetector()
    regex = RegexDetector()
    # Policy with liberal score threshold so the detector sees most candidates
    policy = {"score_threshold": 0.3}

    tp = 0
    fn = 0

    for sample in corpus:
        text: str = sample["text"]
        expected: list[dict] = sample.get("expected", [])

        # Filter annotations for this entity class
        gold_annotations = [
            Annotation(
                entity_type=ann["entity_type"],
                span_start=ann["span_start"],
                span_end=ann["span_end"],
            )
            for ann in expected
            if ann["entity_type"] == entity_type
        ]

        if not gold_annotations:
            continue  # sample has no annotation for this class

        # Run both detectors and merge results
        presidio_findings = asyncio.run(presidio.detect(text, policy))
        regex_findings = asyncio.run(regex.detect(text, policy))
        predictions = presidio_findings + regex_findings

        for gold in gold_annotations:
            if _predictions_hit(predictions, gold):
                tp += 1
            else:
                fn += 1

    total = tp + fn
    recall = tp / total if total > 0 else 0.0
    return EvalResult(entity_type=entity_type, tp=tp, fn=fn, recall=recall)


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus_loaded() -> list[dict]:
    """Verify corpus file exists and return its samples."""
    assert _CORPUS_PATH.exists(), (
        f"Corpus not found at {_CORPUS_PATH}. "
        "Run from the workers/ directory or check PYTHONPATH."
    )
    samples = _load_corpus()
    assert len(samples) >= 200, f"Corpus must have ≥200 samples, found {len(samples)}"
    return samples


@pytest.mark.parametrize("entity_type", PII_ENTITY_CLASSES)
def test_pii_recall_ge_threshold(entity_type: str, corpus_loaded: list[dict]) -> None:
    """Recall for PII *entity_type* must be ≥ PII_RECALL_THRESHOLD (0.95)."""
    result = evaluate_recall(entity_type)
    assert result.tp + result.fn > 0, (
        f"No gold annotations found for {entity_type} in corpus. "
        "Add samples with expected annotations."
    )
    assert result.recall >= PII_RECALL_THRESHOLD, (
        f"Recall for {entity_type} is {result.recall:.3f} "
        f"(TP={result.tp}, FN={result.fn}), "
        f"required ≥ {PII_RECALL_THRESHOLD}"
    )


@pytest.mark.parametrize("entity_type", SECRET_ENTITY_CLASSES)
def test_secret_recall_ge_threshold(entity_type: str, corpus_loaded: list[dict]) -> None:
    """Recall for secret *entity_type* must be ≥ SECRET_RECALL_THRESHOLD (0.99)."""
    result = evaluate_recall(entity_type)
    assert result.tp + result.fn > 0, (
        f"No gold annotations found for {entity_type} in corpus. "
        "Add samples with expected annotations."
    )
    assert result.recall >= SECRET_RECALL_THRESHOLD, (
        f"Recall for {entity_type} is {result.recall:.3f} "
        f"(TP={result.tp}, FN={result.fn}), "
        f"required ≥ {SECRET_RECALL_THRESHOLD}"
    )


@pytest.mark.parametrize("entity_type", ENTITY_CLASSES)
def test_recall_ge_threshold(entity_type: str, corpus_loaded: list[dict]) -> None:
    """Legacy gate: recall for *entity_type* must be ≥ RECALL_THRESHOLD (0.90).

    This test covers all classes with the original baseline threshold.
    The more specific PII/secret tests above apply stricter thresholds.
    """
    result = evaluate_recall(entity_type)
    assert result.tp + result.fn > 0, (
        f"No gold annotations found for {entity_type} in corpus. "
        "Add samples with expected annotations."
    )
    assert result.recall >= RECALL_THRESHOLD, (
        f"Recall for {entity_type} is {result.recall:.3f} "
        f"(TP={result.tp}, FN={result.fn}), "
        f"required ≥ {RECALL_THRESHOLD}"
    )


def test_corpus_has_minimum_samples_per_class(corpus_loaded: list[dict]) -> None:
    """Verify corpus has ≥10 annotated examples per required class."""
    class_counts: dict[str, int] = {cls: 0 for cls in ENTITY_CLASSES}

    for sample in corpus_loaded:
        for ann in sample.get("expected", []):
            et = ann.get("entity_type", "")
            if et in class_counts:
                class_counts[et] += 1

    for cls, count in class_counts.items():
        assert count >= 10, f"Class {cls} has only {count} annotated samples; need ≥10"


def test_corpus_has_200_samples(corpus_loaded: list[dict]) -> None:
    """Corpus must have at least 200 samples (T6 requirement)."""
    assert len(corpus_loaded) >= 200, (
        f"Corpus has {len(corpus_loaded)} samples; T6 requires ≥200"
    )


def test_no_null_findings_from_presidio_detector() -> None:
    """PresidioDetector must never return None or malformed findings."""
    import asyncio
    from workers.ml.presidio_detector import PresidioDetector

    detector = PresidioDetector()
    findings = asyncio.run(
        detector.detect("This is a safe plain text with no PII.", {})
    )
    assert isinstance(findings, list)
    for f in findings:
        assert f.detector
        assert f.rule_id
        assert 0.0 <= f.confidence <= 1.0
        assert f.severity in {"low", "medium", "high", "critical"}


def test_no_null_findings_from_regex_detector() -> None:
    """RegexDetector must never return None or malformed findings."""
    import asyncio
    from workers.ml.regex_detector import RegexDetector

    detector = RegexDetector()
    findings = asyncio.run(
        detector.detect("This is a safe plain text with no secrets.", {})
    )
    assert isinstance(findings, list)
    for f in findings:
        assert f.detector
        assert f.rule_id
        assert 0.0 <= f.confidence <= 1.0
        assert f.severity in {"low", "medium", "high", "critical"}


# Kept for backward compatibility
def test_no_null_findings_from_detector() -> None:
    """Detector must never return None or malformed findings (legacy alias)."""
    test_no_null_findings_from_presidio_detector()
