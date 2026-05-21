"""Prometheus metrics for SafeContext workers.

ADR-009: All observability via OpenTelemetry + Prometheus.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge

# ── Worker task metrics ──────────────────────────────────────────────────────

TASKS_TOTAL = Counter(
    "safecontext_worker_tasks_total",
    "Total number of worker tasks executed",
    ["agent", "status"],  # status: success | failure | skipped
)

TASK_DURATION_SECONDS = Histogram(
    "safecontext_worker_task_duration_seconds",
    "Duration of worker task execution in seconds",
    ["agent"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ── Detection metrics ────────────────────────────────────────────────────────

FINDINGS_TOTAL = Counter(
    "safecontext_findings_total",
    "Total number of findings detected",
    ["entity_type", "severity"],
)

DETECTOR_DURATION_SECONDS = Histogram(
    "safecontext_detector_duration_seconds",
    "Duration of detector.detect() calls",
    ["detector"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

# ── Outbox relay metrics ─────────────────────────────────────────────────────

OUTBOX_EVENTS_RELAYED = Counter(
    "safecontext_outbox_events_relayed_total",
    "Total outbox events relayed to Redis",
    ["event_type"],
)

OUTBOX_RELAY_ERRORS = Counter(
    "safecontext_outbox_relay_errors_total",
    "Errors encountered during outbox relay loop",
)

OUTBOX_LAG_EVENTS = Gauge(
    "safecontext_outbox_lag_events",
    "Number of unprocessed outbox events (approximation)",
)

# ── ML quality metrics ───────────────────────────────────────────────────────

DETECTOR_RECALL = Gauge(
    "safecontext_detector_recall",
    "Recall of the detector for each entity class (evaluated against labeled corpus)",
    ["class"],
)

# ── DLQ metrics ──────────────────────────────────────────────────────────────

DLQ_MESSAGES_TOTAL = Counter(
    "safecontext_dlq_messages_total",
    "Messages sent to the dead-letter queue after max retries",
    ["agent"],
)

dlq_depth = Gauge(
    "safecontext_dlq_depth",
    "Number of messages currently in the Dead Letter Queue",
)
