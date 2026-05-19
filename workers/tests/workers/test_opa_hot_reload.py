"""Tests for OPA hot-reload client and DLQ depth monitor.

AC E2.3:
  - OPA client returns defaults when OPA is unreachable (no crash).
  - OPA client evaluate() posts to OPA with the correct input payload.
  - DLQ monitor updates the Prometheus gauge with the Redis list length.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine synchronously using a fresh event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# OPAClient tests
# ---------------------------------------------------------------------------


class TestOPAClientDefaultPolicy:
    """test_opa_client_returns_default_when_unreachable

    When OPA URL is unreachable (httpx raises ConnectError), get_policy()
    must return the default policy without raising an exception.
    """

    def test_returns_default_policy_when_cache_is_empty(self):
        from workers.core.opa_client import OPAClient

        client = OPAClient(opa_url="http://unreachable-opa:9999")
        result = _run(client.get_policy("base"))

        assert isinstance(result, dict)
        assert "entities" in result
        assert "confidence_threshold" in result
        assert result["confidence_threshold"] == 0.85

    def test_returns_default_policy_after_poll_failure(self):
        """Even after a failed poll attempt the client should remain stable."""
        import httpx
        from workers.core.opa_client import OPAClient

        client = OPAClient(opa_url="http://unreachable-opa:9999")

        async def _run_poll_once():
            # Simulate a single failed refresh without looping
            with patch("httpx.AsyncClient") as mock_cls:
                mock_http = AsyncMock()
                mock_http.__aenter__ = AsyncMock(return_value=mock_http)
                mock_http.__aexit__ = AsyncMock(return_value=False)
                mock_http.get = AsyncMock(
                    side_effect=httpx.ConnectError("connection refused")
                )
                mock_cls.return_value = mock_http
                try:
                    await client._refresh()
                except Exception:
                    pass  # errors must be swallowed by the caller (start_polling)

        _run(_run_poll_once())

        # Policy cache is still empty → must fall back to defaults
        result = _run(client.get_policy("base"))
        assert result["confidence_threshold"] == 0.85

    def test_get_policy_version_returns_unknown_initially(self):
        from workers.core.opa_client import OPAClient

        client = OPAClient(opa_url="http://unreachable-opa:9999")
        version = _run(client.get_policy_version())
        assert version == "unknown"


class TestOPAClientEvaluate:
    """test_opa_client_evaluate

    evaluate() must POST to the correct OPA endpoint with the input wrapped
    in {\"input\": ...} and return the ``result`` field of the response.
    """

    def test_evaluate_posts_to_correct_url(self):
        from workers.core.opa_client import OPAClient

        client = OPAClient(opa_url="http://opa:8181")
        input_data = {"user": "alice", "action": "read"}
        expected_result = {"allow": True}

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"result": expected_result})

        async def _run_evaluate():
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_http):
                result = await client.evaluate("safecontext/policy/allow", input_data)
            return result, mock_http

        result, mock_http = _run(_run_evaluate())

        # Verify POST was called to the right URL
        mock_http.post.assert_called_once_with(
            "http://opa:8181/v1/data/safecontext/policy/allow",
            json={"input": input_data},
        )
        assert result == expected_result

    def test_evaluate_returns_empty_dict_on_missing_result(self):
        from workers.core.opa_client import OPAClient

        client = OPAClient(opa_url="http://opa:8181")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={})  # no "result" key

        async def _run_evaluate():
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=mock_response)

            with patch("httpx.AsyncClient", return_value=mock_http):
                return await client.evaluate("safecontext/policy/allow", {})

        result = _run(_run_evaluate())
        assert result == {}


class TestOPAPollRefreshesCache:
    """Verify that a successful _refresh() populates the policy cache."""

    def test_refresh_populates_cache(self):
        from workers.core.opa_client import OPAClient

        client = OPAClient(opa_url="http://opa:8181")

        policy_data = {
            "entities": ["EMAIL_ADDRESS"],
            "confidence_threshold": 0.90,
        }

        async def _run_refresh():
            def _make_response(status_code, body):
                r = MagicMock()
                r.status_code = status_code
                r.json = MagicMock(return_value=body)
                return r

            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(
                side_effect=[
                    _make_response(200, {"result": {"id": "safecontext-base"}}),
                    _make_response(200, {"result": "1.2.0"}),
                    _make_response(200, {"result": policy_data}),
                ]
            )
            with patch("httpx.AsyncClient", return_value=mock_http):
                await client._refresh()

        _run(_run_refresh())

        cached = _run(client.get_policy("base"))
        assert cached == policy_data
        assert _run(client.get_policy_version()) == "1.2.0"


# ---------------------------------------------------------------------------
# DLQ monitor tests
# ---------------------------------------------------------------------------


class TestDLQMonitorUpdatesGauge:
    """test_dlq_monitor_updates_gauge

    monitor_dlq() must call Redis LLEN on the DLQ key and set the
    safecontext_dlq_depth gauge to the returned depth.
    """

    def test_gauge_set_to_redis_llen(self):
        from workers.core.metrics import dlq_depth

        async def _run_one_iteration():
            mock_redis = AsyncMock()
            mock_redis.llen = AsyncMock(return_value=7)

            with (
                patch("redis.asyncio.from_url", return_value=mock_redis),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                # Patch sleep to raise after one iteration so the loop ends
                mock_sleep.side_effect = asyncio.CancelledError()
                try:
                    from workers import dlq_monitor as mod

                    # Reset the module so patched from_url is used
                    with patch.object(mod, "DLQ_KEY", "dramatiq:safecontext_dl.DQ"):
                        await mod.monitor_dlq()
                except asyncio.CancelledError:
                    pass

            return mock_redis

        mock_redis = _run(_run_one_iteration())

        mock_redis.llen.assert_called()
        # Gauge should reflect the mocked depth
        assert dlq_depth._value.get() == 7.0

    def test_gauge_set_to_zero_when_dlq_empty(self):
        from workers.core.metrics import dlq_depth

        async def _run_one_iteration():
            mock_redis = AsyncMock()
            mock_redis.llen = AsyncMock(return_value=0)

            with (
                patch("redis.asyncio.from_url", return_value=mock_redis),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                mock_sleep.side_effect = asyncio.CancelledError()
                try:
                    from workers import dlq_monitor as mod

                    await mod.monitor_dlq()
                except asyncio.CancelledError:
                    pass

        _run(_run_one_iteration())
        assert dlq_depth._value.get() == 0.0

    def test_monitor_does_not_crash_on_redis_error(self):
        """A Redis error must be swallowed and not propagate out of monitor_dlq."""
        import redis.exceptions

        async def _run_one_iteration():
            mock_redis = AsyncMock()
            mock_redis.llen = AsyncMock(
                side_effect=redis.exceptions.ConnectionError("timeout")
            )

            with (
                patch("redis.asyncio.from_url", return_value=mock_redis),
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                mock_sleep.side_effect = asyncio.CancelledError()
                try:
                    from workers import dlq_monitor as mod

                    await mod.monitor_dlq()
                except asyncio.CancelledError:
                    pass  # expected — loop terminated by mocked sleep
                # If we reach here without another exception the test passes

        _run(_run_one_iteration())
