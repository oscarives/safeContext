from prometheus_client import Counter, Gauge, Histogram

scan_duration = Histogram(
    "safecontext_scan_duration_seconds",
    "Duration of scan operations",
    ["policy_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

findings_total = Counter(
    "safecontext_findings_total",
    "Total findings by class and severity",
    ["entity_class", "severity"],
)

detector_recall = Gauge(
    "safecontext_detector_recall",
    "Detector recall by entity class",
    ["class"],
)

operations_total = Counter(
    "safecontext_operations_total",
    "Total operations by status",
    ["status"],
)
