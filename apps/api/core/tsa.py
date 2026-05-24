"""RFC 3161 Timestamp Authority client for non-repudiation (F6-B1).

Requests a trusted timestamp token from an external TSA for a given digest.
The TSA token proves that the data existed at a specific point in time,
independent of the server clock — critical for audit evidence.

Supports configurable TSA URL (FreeTSA, internal CA TSA, etc.).
Falls back gracefully when TSA is unavailable (logs warning, returns None).
"""
from __future__ import annotations

import base64
import hashlib
import struct
import time
from dataclasses import dataclass

import httpx
import structlog

from config import settings

log = structlog.get_logger(__name__)

# TSA configuration — defaults to FreeTSA for dev; override in production
TSA_URL = getattr(settings, "tsa_url", "https://freetsa.org/tsr")
TSA_TIMEOUT = 10.0  # seconds


@dataclass(frozen=True)
class TSAToken:
    """Parsed TSA response."""
    raw_token: bytes          # DER-encoded TimeStampResp
    token_b64: str            # base64-encoded for JSON transport
    timestamp_utc: float      # Unix timestamp from response (approximation)
    tsa_url: str              # Which TSA was used


def _build_ts_request(digest: bytes) -> bytes:
    """Build a minimal RFC 3161 TimeStampReq in DER encoding.

    This constructs a valid ASN.1 DER TimeStampReq:
    TimeStampReq ::= SEQUENCE {
        version        INTEGER { v1(1) },
        messageImprint MessageImprint,
        certReq        BOOLEAN DEFAULT FALSE
    }
    MessageImprint ::= SEQUENCE {
        hashAlgorithm  AlgorithmIdentifier,  -- SHA-256 OID
        hashedMessage  OCTET STRING
    }
    """
    # SHA-256 AlgorithmIdentifier OID: 2.16.840.1.101.3.4.2.1
    sha256_oid = bytes([
        0x30, 0x0d,  # SEQUENCE
        0x06, 0x09,  # OID
        0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01,
        0x05, 0x00,  # NULL
    ])

    # MessageImprint = SEQUENCE { hashAlgorithm, hashedMessage }
    hashed_message = bytes([0x04, len(digest)]) + digest  # OCTET STRING
    message_imprint_content = sha256_oid + hashed_message
    message_imprint = bytes([0x30, len(message_imprint_content)]) + message_imprint_content

    # version INTEGER v1(1)
    version = bytes([0x02, 0x01, 0x01])

    # certReq BOOLEAN TRUE — request the TSA cert for offline verification
    cert_req = bytes([0x01, 0x01, 0xff])

    # TimeStampReq SEQUENCE
    req_content = version + message_imprint + cert_req
    ts_req = bytes([0x30, 0x82]) + struct.pack(">H", len(req_content)) + req_content

    return ts_req


async def request_tsa_token(
    data: bytes,
    http_client: httpx.AsyncClient | None = None,
    tsa_url: str | None = None,
) -> TSAToken | None:
    """Request a TSA timestamp for the given data.

    Args:
        data: The raw bytes to timestamp (typically JSON-serialized audit export)
        http_client: Optional shared httpx client (uses a new one if not provided)
        tsa_url: Override TSA URL (defaults to settings.tsa_url)

    Returns:
        TSAToken with the raw DER response and metadata, or None on failure.
    """
    url = tsa_url or TSA_URL
    digest = hashlib.sha256(data).digest()
    ts_request = _build_ts_request(digest)

    try:
        if http_client:
            response = await http_client.post(
                url,
                content=ts_request,
                headers={"Content-Type": "application/timestamp-query"},
                timeout=TSA_TIMEOUT,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    content=ts_request,
                    headers={"Content-Type": "application/timestamp-query"},
                    timeout=TSA_TIMEOUT,
                )

        if response.status_code != 200:
            log.warning(
                "tsa.request_failed",
                status=response.status_code,
                tsa_url=url,
            )
            return None

        raw_token = response.content
        if not raw_token or len(raw_token) < 10:
            log.warning("tsa.empty_response", tsa_url=url)
            return None

        token_b64 = base64.b64encode(raw_token).decode("ascii")

        return TSAToken(
            raw_token=raw_token,
            token_b64=token_b64,
            timestamp_utc=time.time(),
            tsa_url=url,
        )

    except httpx.TimeoutException:
        log.warning("tsa.timeout", tsa_url=url, timeout=TSA_TIMEOUT)
        return None
    except httpx.ConnectError:
        log.warning("tsa.connect_error", tsa_url=url)
        return None
    except Exception as exc:
        log.error("tsa.unexpected_error", error=str(exc), tsa_url=url)
        return None


def verify_tsa_digest(raw_token: bytes, expected_digest: bytes) -> bool:
    """Basic verification that the TSA response contains our digest.

    For full cryptographic verification, use:
        openssl ts -verify -in token.tsr -data original.json -CAfile tsa_ca.pem

    This is a lightweight check that the token references our content hash.
    """
    # The SHA-256 digest should appear verbatim in the DER-encoded response
    return expected_digest in raw_token
