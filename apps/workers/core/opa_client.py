"""OPA policy client with hot-reload support.

Polls OPA every POLICY_POLL_INTERVAL seconds and caches the active policy.
Workers call get_policy() to get the current policy without restart.
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from workers.config import settings

log = structlog.get_logger(__name__)


class OPAClient:
    """Async OPA client with background polling for hot-reload of policies.

    The client caches the last-known policy and falls back to sane defaults
    when OPA is unreachable, so workers never block on OPA availability.

    A single persistent httpx.AsyncClient is shared across evaluate() and
    _refresh() calls to avoid creating a new TCP connection per request.
    """

    def __init__(self, opa_url: str) -> None:
        self._url = opa_url
        self._policy_cache: dict = {}
        self._policy_version: str = "unknown"
        self._running: bool = False
        # Persistent client — avoids new TCP connection per evaluate()/poll cycle.
        # Closed in stop() when the singleton is shut down.
        self._http = httpx.AsyncClient(timeout=5.0)

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_policy(self, policy_name: str = "base") -> dict:
        """Return cached policy. Falls back to defaults if OPA is unreachable."""
        return self._policy_cache.get(policy_name, self._default_policy())

    async def get_policy_version(self) -> str:
        """Return the currently cached policy version string."""
        return self._policy_version

    async def evaluate(self, policy_path: str, input_data: dict) -> dict:
        """Evaluate a policy rule with given input.

        Args:
            policy_path: OPA path suffix, e.g. ``safecontext/policy/allow``.
            input_data: Arbitrary dict forwarded as ``input`` to OPA.

        Returns:
            The ``result`` field from the OPA response, or an empty dict on error.
        """
        resp = await self._http.post(
            f"{self._url}/v1/data/{policy_path}",
            json={"input": input_data},
        )
        resp.raise_for_status()
        return resp.json().get("result", {})

    # ── Background polling ────────────────────────────────────────────────────

    async def start_polling(self) -> None:
        """Background task: poll OPA every POLL_INTERVAL seconds.

        Designed to run as an asyncio task.  Errors are logged but never
        propagated — the cache simply retains the last successful value.
        """
        self._running = True
        log.info("opa_client.polling_started", interval_s=settings.policy_poll_interval, url=self._url)
        while self._running:
            try:
                await self._refresh()
            except Exception as exc:  # noqa: BLE001
                log.warning("opa_client.poll_failed", error=str(exc))
            await asyncio.sleep(settings.policy_poll_interval)

    async def stop(self) -> None:
        """Stop the polling loop and close the persistent HTTP client."""
        self._running = False
        await self._http.aclose()
        log.info("opa_client.polling_stopped")

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _refresh(self) -> None:
        """Fetch the current policy version and update the cache.

        OPA 1.x with bundle/volume loading does NOT register policies via
        the /v1/policies API (that endpoint is only for policies pushed via PUT).
        Policies loaded from filesystem bundles are only accessible via /v1/data.
        """
        # Fetch semantic version from policy data (primary source of truth)
        meta_resp = await self._http.get(
            f"{self._url}/v1/data/safecontext/policy/policy_version"
        )
        if meta_resp.status_code == 200:
            self._policy_version = str(
                meta_resp.json().get("result", self._policy_version)
            )

        # Fetch the full base policy bundle for the in-memory cache
        policy_resp = await self._http.get(
            f"{self._url}/v1/data/safecontext/policy"
        )
        if policy_resp.status_code == 200:
            self._policy_cache["base"] = policy_resp.json().get("result", {})
            log.debug("opa_client.policy_refreshed", version=self._policy_version)

    def _default_policy(self) -> dict:
        """Sane defaults used when OPA is unreachable and the cache is empty."""
        return {
            "entities": [
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "PERSON",
                "API_KEY",
                "PASSWORD",
            ],
            # Use the configured threshold instead of a hard-coded literal,
            # so a .env override is respected even when OPA is down.
            "confidence_threshold": settings.detector_confidence_threshold,
        }


# ---------------------------------------------------------------------------
# Module-level singleton — imported by workers
# ---------------------------------------------------------------------------

opa_client = OPAClient(settings.opa_url)
