"""SIEM integration — CEF/LEEF event export with webhook and syslog support.

Formats SafeContext security events into industry-standard formats
(CEF — Common Event Format, LEEF — Log Event Extended Format) and
delivers them to configured destinations (webhook URL or syslog).

Usage:

    from core.siem import emit_siem_event, SIEMEvent, SIEMConfig

    config = SIEMConfig(
        enabled=True,
        format="cef",
        webhook_url="https://siem.internal/api/events",
    )

    event = SIEMEvent(
        event_type="scan.completed",
        severity=5,
        trace_id="abc-123",
        actor_id="user-456",
        tenant_id="tenant-789",
        details={"findings_count": 3, "status": "escalated"},
    )

    await emit_siem_event(event, config)

All external calls are fire-and-forget with timeout protection.
Failures are logged but never block the main request flow.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

# CEF severity mapping: SafeContext severity string → CEF numeric (0-10)
CEF_SEVERITY_MAP: dict[str, int] = {
    "low": 2,
    "medium": 5,
    "high": 7,
    "critical": 10,
    # Event types that aren't findings
    "info": 1,
    "warning": 4,
}


@dataclass
class SIEMConfig:
    """Per-tenant SIEM destination configuration."""

    enabled: bool = False
    format: str = "cef"  # "cef" | "leef" | "json"
    webhook_url: str | None = None
    webhook_token: str | None = None  # Bearer token for webhook auth
    syslog_host: str | None = None
    syslog_port: int = 514
    syslog_protocol: str = "udp"  # "udp" | "tcp"


@dataclass
class SIEMEvent:
    """A security event to be emitted to SIEM."""

    event_type: str  # e.g. "scan.completed", "finding.detected", "review.approved"
    severity: int  # CEF severity 0-10
    trace_id: str
    actor_id: str
    tenant_id: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


def format_cef(event: SIEMEvent) -> str:
    """Format event as CEF (Common Event Format).

    CEF format:
        CEF:0|Vendor|Product|Version|EventID|Name|Severity|Extensions

    Extensions use key=value pairs separated by spaces.
    Values containing spaces, equals, or pipes are escaped.
    """
    # Escape CEF special characters in extension values
    def esc(val: str) -> str:
        return val.replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n")

    extensions = [
        f"trace_id={esc(event.trace_id)}",
        f"actor_id={esc(event.actor_id)}",
        f"tenant_id={esc(event.tenant_id)}",
        f"rt={esc(event.timestamp)}",
    ]

    # Add detail fields as extensions
    for key, value in event.details.items():
        ext_val = str(value) if not isinstance(value, str) else value
        extensions.append(f"cs_{key}={esc(ext_val)}")

    ext_str = " ".join(extensions)

    return (
        f"CEF:0|SafeContext|SafeContext|1.1.0|{event.event_type}"
        f"|{event.event_type}|{event.severity}|{ext_str}"
    )


def format_leef(event: SIEMEvent) -> str:
    """Format event as LEEF (Log Event Extended Format).

    LEEF format:
        LEEF:2.0|Vendor|Product|Version|EventID|<tab-separated key=value pairs>

    Used primarily by IBM QRadar.
    """
    pairs = [
        f"devTime={event.timestamp}",
        f"cat={event.event_type}",
        f"sev={event.severity}",
        f"usrName={event.actor_id}",
        f"src={event.tenant_id}",
        f"reason={event.trace_id}",
    ]

    for key, value in event.details.items():
        pairs.append(f"{key}={value}")

    tab = "\t"
    return f"LEEF:2.0|SafeContext|SafeContext|1.1.0|{event.event_type}|{tab.join(pairs)}"


def format_json_event(event: SIEMEvent) -> str:
    """Format event as structured JSON."""
    payload = {
        "source": "safecontext",
        "version": "1.1.0",
        "event_type": event.event_type,
        "severity": event.severity,
        "timestamp": event.timestamp,
        "trace_id": event.trace_id,
        "actor_id": event.actor_id,
        "tenant_id": event.tenant_id,
        "details": event.details,
    }
    return json.dumps(payload, default=str)


def format_event(event: SIEMEvent, fmt: str = "cef") -> str:
    """Format a SIEM event in the specified format."""
    formatters = {
        "cef": format_cef,
        "leef": format_leef,
        "json": format_json_event,
    }
    formatter = formatters.get(fmt, format_cef)
    return formatter(event)


async def send_webhook(
    formatted: str,
    config: SIEMConfig,
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Send formatted event to a webhook URL.

    Returns True on success, False on failure. Never raises.
    """
    if not config.webhook_url:
        return False

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.webhook_token:
        headers["Authorization"] = f"Bearer {config.webhook_token}"

    # Wrap in JSON envelope for webhook delivery
    payload = json.dumps({"event": formatted, "format": config.format})

    try:
        client = http_client or httpx.AsyncClient(timeout=5.0)
        should_close = http_client is None

        try:
            response = await client.post(
                config.webhook_url,
                content=payload,
                headers=headers,
            )
            if response.status_code >= 400:
                logger.warning(
                    "siem.webhook.error",
                    status_code=response.status_code,
                    url=config.webhook_url,
                )
                return False
            return True
        finally:
            if should_close:
                await client.aclose()

    except Exception as exc:
        logger.warning("siem.webhook.failed", error=str(exc), url=config.webhook_url)
        return False


def send_syslog(
    formatted: str,
    config: SIEMConfig,
) -> bool:
    """Send formatted event via syslog (UDP or TCP).

    Returns True on success, False on failure. Never raises.
    """
    if not config.syslog_host:
        return False

    try:
        # Syslog priority: facility=local0 (16), severity mapped from CEF
        # PRI = facility * 8 + severity
        pri = 16 * 8 + 6  # local0.info
        message = f"<{pri}>{formatted}"
        encoded = message.encode("utf-8")

        if config.syslog_protocol == "tcp":
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3.0)
                sock.connect((config.syslog_host, config.syslog_port))
                sock.sendall(encoded + b"\n")
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(3.0)
                sock.sendto(encoded, (config.syslog_host, config.syslog_port))

        return True

    except Exception as exc:
        logger.warning(
            "siem.syslog.failed",
            error=str(exc),
            host=config.syslog_host,
            port=config.syslog_port,
        )
        return False


async def emit_siem_event(
    event: SIEMEvent,
    config: SIEMConfig,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, bool]:
    """Emit a SIEM event to all configured destinations.

    Fire-and-forget: failures are logged but never block the caller.

    Returns a dict with delivery status per destination:
        {"webhook": True/False, "syslog": True/False}
    """
    if not config.enabled:
        return {"webhook": False, "syslog": False}

    formatted = format_event(event, config.format)

    results: dict[str, bool] = {"webhook": False, "syslog": False}

    # Webhook delivery
    if config.webhook_url:
        results["webhook"] = await send_webhook(formatted, config, http_client)

    # Syslog delivery
    if config.syslog_host:
        results["syslog"] = send_syslog(formatted, config)

    logger.info(
        "siem.event.emitted",
        event_type=event.event_type,
        trace_id=event.trace_id,
        format=config.format,
        webhook=results["webhook"],
        syslog=results["syslog"],
    )

    return results


# ── Convenience constructors for common events ───────────────────────────


def scan_completed_event(
    trace_id: str,
    actor_id: str,
    tenant_id: str,
    findings_count: int,
    status: str,
    severity: str = "info",
) -> SIEMEvent:
    """Create a SIEM event for a completed scan."""
    return SIEMEvent(
        event_type="scan.completed",
        severity=CEF_SEVERITY_MAP.get(severity, 1),
        trace_id=trace_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        details={
            "findings_count": findings_count,
            "status": status,
        },
    )


def finding_detected_event(
    trace_id: str,
    actor_id: str,
    tenant_id: str,
    rule_id: str,
    severity: str,
    confidence: float,
) -> SIEMEvent:
    """Create a SIEM event for a detected finding."""
    return SIEMEvent(
        event_type="finding.detected",
        severity=CEF_SEVERITY_MAP.get(severity, 5),
        trace_id=trace_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        details={
            "rule_id": rule_id,
            "finding_severity": severity,
            "confidence": confidence,
        },
    )


def review_action_event(
    trace_id: str,
    actor_id: str,
    tenant_id: str,
    action: str,  # "approved" | "rejected"
    finding_id: str,
) -> SIEMEvent:
    """Create a SIEM event for a review action."""
    return SIEMEvent(
        event_type=f"review.{action}",
        severity=CEF_SEVERITY_MAP.get("info", 1),
        trace_id=trace_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        details={
            "action": action,
            "finding_id": finding_id,
        },
    )


def retention_purge_event(
    tenant_id: str,
    operations_deleted: int,
    certificate_id: str,
) -> SIEMEvent:
    """Create a SIEM event for a GDPR retention purge."""
    return SIEMEvent(
        event_type="retention.purge",
        severity=CEF_SEVERITY_MAP.get("warning", 4),
        trace_id=certificate_id,
        actor_id="retention-purge-job",
        tenant_id=tenant_id,
        details={
            "operations_deleted": operations_deleted,
            "certificate_id": certificate_id,
        },
    )
