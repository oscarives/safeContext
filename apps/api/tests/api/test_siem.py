"""Tests for F6-C6 SIEM integration — CEF/LEEF formatting, webhook, syslog.

All external calls are mocked.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.siem import (
    CEF_SEVERITY_MAP,
    SIEMConfig,
    SIEMEvent,
    emit_siem_event,
    finding_detected_event,
    format_cef,
    format_event,
    format_json_event,
    format_leef,
    retention_purge_event,
    review_action_event,
    scan_completed_event,
    send_syslog,
    send_webhook,
)


# ── CEF formatting tests ─────────────────────────────────────────────────────


class TestFormatCEF:
    def test_basic_cef_format(self):
        event = SIEMEvent(
            event_type="scan.completed",
            severity=5,
            trace_id="trace-abc",
            actor_id="actor-123",
            tenant_id="tenant-xyz",
            timestamp="2026-01-01T00:00:00",
        )
        cef = format_cef(event)
        assert cef.startswith("CEF:0|SafeContext|SafeContext|1.1.0|scan.completed|scan.completed|5|")
        assert "trace_id=trace-abc" in cef
        assert "actor_id=actor-123" in cef
        assert "tenant_id=tenant-xyz" in cef

    def test_cef_escapes_special_chars(self):
        event = SIEMEvent(
            event_type="test",
            severity=1,
            trace_id="a=b",
            actor_id="c\\d",
            tenant_id="t",
            details={"msg": "hello\nworld"},
        )
        cef = format_cef(event)
        assert "a\\=b" in cef
        assert "c\\\\d" in cef
        assert "hello\\nworld" in cef

    def test_cef_includes_details_as_extensions(self):
        event = SIEMEvent(
            event_type="finding.detected",
            severity=7,
            trace_id="t",
            actor_id="a",
            tenant_id="tn",
            details={"rule_id": "API_KEY", "confidence": 0.95},
        )
        cef = format_cef(event)
        assert "cs_rule_id=API_KEY" in cef
        assert "cs_confidence=0.95" in cef


class TestFormatLEEF:
    def test_basic_leef_format(self):
        event = SIEMEvent(
            event_type="scan.completed",
            severity=5,
            trace_id="trace-1",
            actor_id="user-1",
            tenant_id="tenant-1",
        )
        leef = format_leef(event)
        assert leef.startswith("LEEF:2.0|SafeContext|SafeContext|1.1.0|scan.completed|")
        assert "usrName=user-1" in leef
        assert "reason=trace-1" in leef
        assert "sev=5" in leef

    def test_leef_includes_details(self):
        event = SIEMEvent(
            event_type="finding.detected",
            severity=7,
            trace_id="t",
            actor_id="a",
            tenant_id="tn",
            details={"rule_id": "SSN", "finding_severity": "high"},
        )
        leef = format_leef(event)
        assert "rule_id=SSN" in leef
        assert "finding_severity=high" in leef


class TestFormatJSON:
    def test_json_structure(self):
        event = SIEMEvent(
            event_type="review.approved",
            severity=1,
            trace_id="t-1",
            actor_id="a-1",
            tenant_id="tn-1",
            details={"action": "approved"},
        )
        result = format_json_event(event)
        parsed = json.loads(result)
        assert parsed["source"] == "safecontext"
        assert parsed["version"] == "1.1.0"
        assert parsed["event_type"] == "review.approved"
        assert parsed["details"]["action"] == "approved"


class TestFormatEvent:
    def test_cef_format_selection(self):
        event = SIEMEvent(event_type="test", severity=1, trace_id="t", actor_id="a", tenant_id="tn")
        assert format_event(event, "cef").startswith("CEF:0")

    def test_leef_format_selection(self):
        event = SIEMEvent(event_type="test", severity=1, trace_id="t", actor_id="a", tenant_id="tn")
        assert format_event(event, "leef").startswith("LEEF:2.0")

    def test_json_format_selection(self):
        event = SIEMEvent(event_type="test", severity=1, trace_id="t", actor_id="a", tenant_id="tn")
        parsed = json.loads(format_event(event, "json"))
        assert parsed["source"] == "safecontext"

    def test_unknown_format_falls_back_to_cef(self):
        event = SIEMEvent(event_type="test", severity=1, trace_id="t", actor_id="a", tenant_id="tn")
        assert format_event(event, "unknown").startswith("CEF:0")


# ── Webhook delivery tests ───────────────────────────────────────────────────


class TestSendWebhook:
    @pytest.mark.asyncio
    async def test_success(self):
        config = SIEMConfig(enabled=True, webhook_url="https://siem.test/events")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await send_webhook("CEF:0|test", config, http_client=mock_client)
        assert result is True
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_auth_token(self):
        config = SIEMConfig(
            enabled=True,
            webhook_url="https://siem.test/events",
            webhook_token="secret-token",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        await send_webhook("CEF:0|test", config, http_client=mock_client)
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["Authorization"] == "Bearer secret-token"

    @pytest.mark.asyncio
    async def test_http_error(self):
        config = SIEMConfig(enabled=True, webhook_url="https://siem.test/events")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await send_webhook("CEF:0|test", config, http_client=mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_connection_error(self):
        import httpx

        config = SIEMConfig(enabled=True, webhook_url="https://siem.test/events")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        result = await send_webhook("CEF:0|test", config, http_client=mock_client)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_url_returns_false(self):
        config = SIEMConfig(enabled=True, webhook_url=None)
        result = await send_webhook("CEF:0|test", config)
        assert result is False


# ── Syslog delivery tests ────────────────────────────────────────────────────


class TestSendSyslog:
    def test_udp_success(self):
        config = SIEMConfig(
            enabled=True,
            syslog_host="127.0.0.1",
            syslog_port=514,
            syslog_protocol="udp",
        )

        with patch("core.siem.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = send_syslog("CEF:0|test", config)

        assert result is True

    def test_tcp_success(self):
        config = SIEMConfig(
            enabled=True,
            syslog_host="127.0.0.1",
            syslog_port=1514,
            syslog_protocol="tcp",
        )

        with patch("core.siem.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = send_syslog("CEF:0|test", config)

        assert result is True

    def test_no_host_returns_false(self):
        config = SIEMConfig(enabled=True, syslog_host=None)
        result = send_syslog("CEF:0|test", config)
        assert result is False

    def test_connection_failure_graceful(self):
        config = SIEMConfig(
            enabled=True,
            syslog_host="unreachable",
            syslog_port=514,
        )

        with patch("core.siem.socket.socket") as mock_sock_cls:
            mock_sock_cls.return_value.__enter__ = MagicMock(
                side_effect=OSError("Connection refused")
            )
            result = send_syslog("CEF:0|test", config)

        assert result is False


# ── End-to-end emit tests ────────────────────────────────────────────────────


class TestEmitSIEMEvent:
    @pytest.mark.asyncio
    async def test_disabled_config(self):
        event = SIEMEvent(event_type="test", severity=1, trace_id="t", actor_id="a", tenant_id="tn")
        config = SIEMConfig(enabled=False)

        result = await emit_siem_event(event, config)
        assert result == {"webhook": False, "syslog": False}

    @pytest.mark.asyncio
    async def test_webhook_and_syslog(self):
        event = SIEMEvent(event_type="scan.completed", severity=5, trace_id="t", actor_id="a", tenant_id="tn")
        config = SIEMConfig(
            enabled=True,
            format="cef",
            webhook_url="https://siem.test/events",
            syslog_host="127.0.0.1",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("core.siem.send_syslog", return_value=True):
            result = await emit_siem_event(event, config, http_client=mock_client)

        assert result["webhook"] is True
        assert result["syslog"] is True


# ── Convenience constructor tests ────────────────────────────────────────────


class TestEventConstructors:
    def test_scan_completed_event(self):
        event = scan_completed_event("t1", "a1", "tn1", 3, "escalated", "high")
        assert event.event_type == "scan.completed"
        assert event.severity == CEF_SEVERITY_MAP["high"]
        assert event.details["findings_count"] == 3

    def test_finding_detected_event(self):
        event = finding_detected_event("t1", "a1", "tn1", "API_KEY", "critical", 0.99)
        assert event.event_type == "finding.detected"
        assert event.severity == CEF_SEVERITY_MAP["critical"]
        assert event.details["rule_id"] == "API_KEY"

    def test_review_action_event(self):
        event = review_action_event("t1", "a1", "tn1", "approved", "f-123")
        assert event.event_type == "review.approved"
        assert event.details["finding_id"] == "f-123"

    def test_retention_purge_event(self):
        event = retention_purge_event("tn1", 10, "cert-abc")
        assert event.event_type == "retention.purge"
        assert event.details["operations_deleted"] == 10
        assert event.actor_id == "retention-purge-job"

    def test_siem_event_auto_timestamp(self):
        event = SIEMEvent(event_type="test", severity=1, trace_id="t", actor_id="a", tenant_id="tn")
        assert event.timestamp != ""
        assert "T" in event.timestamp  # ISO format
