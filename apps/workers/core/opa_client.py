"""OPA policy client with hot-reload support.

Polls OPA every POLICY_POLL_INTERVAL seconds and caches the active policy.
Workers call get_policy() to get the current policy without restart.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog

log = structlog.get_logger()

POLL_INTERVAL: int = int(os.environ.get("POLICY_POLL_INTERVAL", "30"))


class OPAClient:
    """Async OPA client with background polling for hot-reload of policies.

    The client caches the last-known policy and falls back to sane defaults
    when OPA is unreachable, so workers never block on OPA availability.
    """

    def __init__(self, opa_url: str) -> None:
        self._url = opa_url
        self._policy_cache: dict = {}
        self._policy_version: str = "unknown"
        self._running: bool = False

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
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
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
        log.info("opa_client.polling_started", interval_s=POLL_INTERVAL, url=self._url)
        while self._running:
            try:
                await self._refresh()
            except Exception as exc:  # noqa: BLE001
                log.warning("opa_client.poll_failed", error=str(exc))
            await asyncio.sleep(POLL_INTERVAL)

    async def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False
        log.info("opa_client.polling_stopped")

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _refresh(self) -> None:
        """Fetch the current policy version and update the cache."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{self._url}/v1/policies/safecontext-base")
            if resp.status_code == 200:
                data = resp.json()
                self._policy_version = data.get("result", {}).get("id", "unknown")

                # Attempt to fetch semantic version from policy data
                meta_resp = await client.get(
                    f"{self._url}/v1/data/safecontext/policy/policy_version"
                )
                if meta_resp.status_code == 200:
                    self._policy_version = meta_resp.json().get(
                        "result", self._policy_version
                    )

                # Fetch the full base policy bundle for the cache
                policy_resp = await client.get(
                    f"{self._url}/v1/data/safecontext/policy"
                )
                if policy_resp.status_code == 200:
                    self._policy_cache["base"] = policy_resp.json().get("result", {})

                log.debug("opa_client.policy_refreshed", version=self._policy_version)

    @staticmethod
    def _default_policy() -> dict:
        """Sane defaults used when OPA is unreachable and the cache is empty."""
        return {
            "entities": [
                "EMAIL_ADDRESS",
                "PHONE_NUMBER",
                "PERSON",
                "API_KEY",
                "PASSWORD",
            ],
            "confidence_threshold": 0.85,
        }


# ---------------------------------------------------------------------------
# Module-level singleton — imported by workers
# ---------------------------------------------------------------------------

opa_client = OPAClient(os.environ.get("OPA_URL", "http://opa:8181"))
