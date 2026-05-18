"""Recall evaluator — runs periodically to update safecontext_detector_recall gauge.

ADR-009: recall is a first-class Prometheus metric, not an afterthought.
DOC-3 gates: recall >= 0.90 (F1), >= 0.95 (F2), >= 0.98 (F5).

This module:
1. Loads the labeled corpus from tests/fixtures/corpus/corpus.json
2. Runs PresidioDetector.detect() against each sample
3. Computes recall per entity class
4. Sets the DETECTOR_RECALL gauge for Prometheus to scrape
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import structlog

log = structlog.get_logger()

# Path to corpus — relative to this file (workers/ml/ → workers/tests/fixtures/corpus/)
_CORPUS_PATH = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "corpus" / "corpus.json"

# Interval between evaluations (default: every 5 minutes)
EVAL_INTERVAL_SECONDS = int(os.environ.get("RECALL_EVAL_INTERVAL", "300"))


def _compute_recall(samples: list[dict], entity_class: str, detector) -> float:
    """Compute recall for a single entity class against labeled samples."""
    true_positive = 0
    false_negative = 0

    for sample in samples:
        expected = [
            e for e in sample.get("expected", [])
            if e.get("entity_type") == entity_class
        ]
        if not expected:
            continue

        # Run detection synchronously (corpus eval runs in executor)
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            findings = loop.run_until_complete(detector.detect(sample["text"], {}))
        finally:
            loop.close()

        detected_spans = {
            (f.span_start, f.span_end)
            for f in findings
            if entity_class in f.detector
        }

        for exp in expected:
            exp_span = (exp["span_start"], exp["span_end"])
            # IoU-based match: spans overlap significantly
            hit = any(
                _iou(exp_span, det_span) >= 0.5
                for det_span in detected_spans
            )
            if hit:
                true_positive += 1
            else:
                false_negative += 1

    total = true_positive + false_negative
    return true_positive / total if total > 0 else 0.0


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Intersection over Union for two spans."""
    inter_start = max(a[0], b[0])
    inter_end = min(a[1], b[1])
    if inter_end <= inter_start:
        return 0.0
    inter = inter_end - inter_start
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def evaluate_and_update_gauge() -> dict[str, float]:
    """Evaluate recall for all classes and update Prometheus gauge.

    Returns: {entity_class: recall_value}
    """
    from workers.core.metrics import DETECTOR_RECALL
    from workers.ml.presidio_detector import PresidioDetector

    if not _CORPUS_PATH.exists():
        log.warning("recall_evaluator.corpus_not_found", path=str(_CORPUS_PATH))
        return {}

    try:
        with open(_CORPUS_PATH, encoding="utf-8") as f:
            corpus = json.load(f)
    except Exception as exc:
        log.error("recall_evaluator.corpus_load_error", error=str(exc))
        return {}

    samples = corpus.get("samples", [])
    if not samples:
        log.warning("recall_evaluator.empty_corpus")
        return {}

    # Determine entity classes from corpus
    classes = {
        e["entity_type"]
        for s in samples
        for e in s.get("expected", [])
    }

    detector = PresidioDetector()
    results: dict[str, float] = {}

    for entity_class in sorted(classes):
        try:
            recall = _compute_recall(samples, entity_class, detector)
            DETECTOR_RECALL.labels(**{"class": entity_class}).set(recall)
            results[entity_class] = recall
            log.info(
                "recall_evaluator.updated",
                entity_class=entity_class,
                recall=round(recall, 3),
            )
        except Exception as exc:
            log.error("recall_evaluator.class_error", entity_class=entity_class, error=str(exc))

    return results


async def run_recall_loop() -> None:
    """Background loop: evaluate recall every EVAL_INTERVAL_SECONDS."""
    import concurrent.futures

    log.info("recall_evaluator.loop_started", interval=EVAL_INTERVAL_SECONDS)

    # Run first evaluation immediately at startup
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="recall-eval")

    while True:
        try:
            results = await loop.run_in_executor(executor, evaluate_and_update_gauge)
            log.info("recall_evaluator.cycle_complete", classes=len(results))
        except Exception as exc:
            log.error("recall_evaluator.loop_error", error=str(exc))

        await asyncio.sleep(EVAL_INTERVAL_SECONDS)
