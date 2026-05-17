"""Internal authentication token for API ↔ worker communication.

Generates short-lived JWT tokens (5 min TTL) signed with the API secret key.
Workers validate these tokens before accepting messages from the API.
This implements Zero Trust for intra-cluster communication (ADR: RNF-SEC-01).
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid

import structlog

log = structlog.get_logger()

_SECRET = os.environ.get("API_SECRET_KEY", "")
TOKEN_TTL_SECONDS = 300  # 5 minutes


def _now() -> int:
    return int(time.time())


def generate_internal_token(service: str = "api") -> str:
    """Generate a short-lived HMAC-signed token for intra-service auth.

    Token format: base64url(payload).signature
    Simple enough for internal use without JWT library dependency.
    """
    payload = {
        "iss": service,
        "iat": _now(),
        "exp": _now() + TOKEN_TTL_SECONDS,
        "jti": str(uuid.uuid4()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
    return f"{encoded}.{sig}"


def verify_internal_token(token: str) -> bool:
    """Verify a short-lived internal token. Returns True if valid and not expired."""
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        encoded, sig = parts
        # Pad base64 if needed
        padding = 4 - len(encoded) % 4
        payload_bytes = base64.urlsafe_b64decode(encoded + "=" * padding)
        expected_sig = hmac.new(_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            log.warning("internal_auth.invalid_signature")
            return False
        payload = json.loads(payload_bytes)
        if payload.get("exp", 0) < _now():
            log.warning("internal_auth.token_expired")
            return False
        return True
    except Exception as exc:
        log.error("internal_auth.verify_error", error=str(exc))
        return False
