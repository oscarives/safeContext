"""OpenBao/Vault Transit engine client for digital signatures (F6-B3).

Signs data using an asymmetric key managed by OpenBao Transit.
The public key is exportable for offline verification without vault access.

Configuration:
    VAULT_ADDR: OpenBao server URL
    VAULT_DEV_TOKEN: Authentication token
    vault_transit_key: Key name in Transit engine (default: safecontext-signing)

Usage:
    signature = await sign_data(data_bytes)
    public_key = await get_public_key()
"""
from __future__ import annotations

import base64

import httpx
import structlog

from config import settings

log = structlog.get_logger(__name__)

VAULT_ADDR = settings.vault_addr
VAULT_TOKEN = settings.vault_dev_token
TRANSIT_KEY = settings.vault_transit_key
VAULT_TIMEOUT = 5.0


def _vault_headers() -> dict[str, str]:
    """Return headers for Vault API requests."""
    return {
        "X-Vault-Token": VAULT_TOKEN,
        "Content-Type": "application/json",
    }


async def _ensure_transit_key(http_client: httpx.AsyncClient | None = None) -> bool:
    """Ensure the Transit signing key exists; create it if not.

    Returns True if key exists/was created, False on failure.
    This is idempotent — safe to call on every startup.
    """
    url = f"{VAULT_ADDR}/v1/transit/keys/{TRANSIT_KEY}"

    try:
        if http_client:
            # Check if key exists
            resp = await http_client.get(url, headers=_vault_headers(), timeout=VAULT_TIMEOUT)
            if resp.status_code == 200:
                return True
            # Create key
            resp = await http_client.post(
                url,
                headers=_vault_headers(),
                json={"type": "ecdsa-p256", "exportable": True},
                timeout=VAULT_TIMEOUT,
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=_vault_headers(), timeout=VAULT_TIMEOUT)
                if resp.status_code == 200:
                    return True
                resp = await client.post(
                    url,
                    headers=_vault_headers(),
                    json={"type": "ecdsa-p256", "exportable": True},
                    timeout=VAULT_TIMEOUT,
                )

        return resp.status_code in (200, 204)
    except Exception as exc:
        log.warning("vault_transit.ensure_key_failed", error=str(exc))
        return False


async def sign_data(
    data: bytes,
    http_client: httpx.AsyncClient | None = None,
    key_name: str | None = None,
) -> str | None:
    """Sign data using Vault Transit engine.

    Args:
        data: Raw bytes to sign
        http_client: Shared httpx client (creates new one if not provided)
        key_name: Override key name (defaults to settings.vault_transit_key)

    Returns:
        Base64-encoded signature, or None if signing fails.
    """
    key = key_name or TRANSIT_KEY
    url = f"{VAULT_ADDR}/v1/transit/sign/{key}"

    # Vault Transit expects base64-encoded input
    input_b64 = base64.b64encode(data).decode("ascii")

    payload = {
        "input": input_b64,
        "hash_algorithm": "sha2-256",
        "signature_algorithm": "pkcs1v15",
    }

    try:
        if http_client:
            resp = await http_client.post(
                url,
                headers=_vault_headers(),
                json=payload,
                timeout=VAULT_TIMEOUT,
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=_vault_headers(),
                    json=payload,
                    timeout=VAULT_TIMEOUT,
                )

        if resp.status_code != 200:
            log.warning(
                "vault_transit.sign_failed",
                status=resp.status_code,
                key=key,
            )
            return None

        result = resp.json()
        # Vault returns signature as "vault:v1:<base64>"
        sig = result.get("data", {}).get("signature", "")
        if sig.startswith("vault:"):
            # Extract the raw base64 part after "vault:vN:"
            parts = sig.split(":", 2)
            sig = parts[2] if len(parts) == 3 else sig

        return sig

    except httpx.TimeoutException:
        log.warning("vault_transit.timeout", key=key)
        return None
    except httpx.ConnectError:
        log.warning("vault_transit.connect_error", key=key)
        return None
    except Exception as exc:
        log.error("vault_transit.unexpected_error", error=str(exc), key=key)
        return None


async def get_public_key(
    http_client: httpx.AsyncClient | None = None,
    key_name: str | None = None,
) -> dict | None:
    """Export the public key for offline signature verification.

    Returns dict with 'algorithm', 'public_key_pem', and 'key_version'.
    """
    key = key_name or TRANSIT_KEY
    url = f"{VAULT_ADDR}/v1/transit/keys/{key}"

    try:
        if http_client:
            resp = await http_client.get(
                url, headers=_vault_headers(), timeout=VAULT_TIMEOUT,
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url, headers=_vault_headers(), timeout=VAULT_TIMEOUT,
                )

        if resp.status_code != 200:
            log.warning("vault_transit.get_key_failed", status=resp.status_code, key=key)
            return None

        data = resp.json().get("data", {})
        keys = data.get("keys", {})
        # Get the latest version
        latest_version = str(max(int(v) for v in keys.keys())) if keys else "1"
        key_data = keys.get(latest_version, {})

        return {
            "algorithm": data.get("type", "unknown"),
            "public_key_pem": key_data.get("public_key", ""),
            "key_version": int(latest_version),
            "name": key,
        }

    except Exception as exc:
        log.warning("vault_transit.get_public_key_failed", error=str(exc))
        return None


async def verify_signature(
    data: bytes,
    signature: str,
    http_client: httpx.AsyncClient | None = None,
    key_name: str | None = None,
) -> bool:
    """Verify a signature using Vault Transit engine.

    Args:
        data: Original data bytes
        signature: Base64-encoded signature to verify
        http_client: Shared httpx client
        key_name: Override key name

    Returns:
        True if signature is valid, False otherwise.
    """
    key = key_name or TRANSIT_KEY
    url = f"{VAULT_ADDR}/v1/transit/verify/{key}"

    input_b64 = base64.b64encode(data).decode("ascii")
    # Vault expects signature in "vault:v1:<sig>" format
    vault_sig = f"vault:v1:{signature}" if not signature.startswith("vault:") else signature

    payload = {
        "input": input_b64,
        "signature": vault_sig,
        "hash_algorithm": "sha2-256",
    }

    try:
        if http_client:
            resp = await http_client.post(
                url, headers=_vault_headers(), json=payload, timeout=VAULT_TIMEOUT,
            )
        else:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url, headers=_vault_headers(), json=payload, timeout=VAULT_TIMEOUT,
                )

        if resp.status_code != 200:
            return False

        return resp.json().get("data", {}).get("valid", False)

    except Exception:
        return False
