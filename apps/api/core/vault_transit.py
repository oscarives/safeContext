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

    F7-3 (H4): the key is created as non-exportable (sign-only). For
    non-repudiation the private key must never leave Vault's Transit boundary;
    the public key is still exportable via the /keys endpoint for offline
    verification. NOTE: keys previously created with exportable=True are NOT
    downgraded automatically — they must be rotated to a fresh non-exportable
    key (new key name, re-seal new operations, keep the old public key to verify
    historical evidence).
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
                json={"type": "ecdsa-p256", "exportable": False},
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
                    json={"type": "ecdsa-p256", "exportable": False},
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

    # F7-1 (H6): the signing key is ecdsa-p256. `signature_algorithm` (pkcs1v15)
    # is an RSA-only parameter — Vault ignores it for ECDSA keys, but sending it
    # is misleading. We omit it so the request reflects the actual key type and
    # Vault uses the correct ECDSA scheme.
    payload = {
        "input": input_b64,
        "hash_algorithm": "sha2-256",
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
    key_version: int = 1,
) -> bool:
    """Verify a signature using Vault Transit engine.

    Args:
        data: Original data bytes
        signature: Base64-encoded signature to verify. May be either a raw
            base64 string (as returned by ``sign_data``) or a fully-qualified
            ``vault:vN:<sig>`` token.
        http_client: Shared httpx client
        key_name: Override key name
        key_version: Transit key version that produced the signature. Used to
            build the ``vault:vN:`` prefix when ``signature`` is a raw base64
            string. Defaults to 1 for backward compatibility.

    Returns:
        True if signature is valid, False otherwise.

    F7-2 (H5): the key version is no longer hardcoded to v1. When the signature
    already carries a ``vault:vN:`` prefix it is honoured verbatim; otherwise the
    prefix is built from ``key_version`` so signatures made with rotated keys
    (v2+) can be verified against historical evidence.
    """
    key = key_name or TRANSIT_KEY
    url = f"{VAULT_ADDR}/v1/transit/verify/{key}"

    input_b64 = base64.b64encode(data).decode("ascii")
    # Honour an explicit "vault:vN:" prefix; otherwise build it from key_version.
    vault_sig = signature if signature.startswith("vault:") else f"vault:v{key_version}:{signature}"

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
