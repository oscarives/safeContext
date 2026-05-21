"""OIDC authentication middleware for SafeContext API.

Validates JWT tokens issued by Keycloak.
Enforces MFA (verified by amr claim containing 'otp').
Provides role-based access control via JWT realm_access.roles.
"""

from __future__ import annotations

import time
from collections import defaultdict
from functools import lru_cache
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from config import settings

log = structlog.get_logger()
_bearer = HTTPBearer(auto_error=False)

# Read from the shared Settings object (picks up .env + type validation)
# instead of raw os.environ.get which bypasses Pydantic validation.
KEYCLOAK_URL = settings.keycloak_url
KEYCLOAK_REALM = settings.keycloak_realm
KEYCLOAK_CLIENT_ID = settings.keycloak_client_id

# Rate limiting state (per client_id, in-memory for single instance; Redis in F4 HA)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
MCP_RATE_LIMIT_RPM = settings.mcp_rate_limit_rpm


@lru_cache(maxsize=1)
def _get_jwks() -> dict:
    """Fetch JWKS from Keycloak (cached, refreshed on cache miss)."""
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def _decode_token(token: str) -> dict:
    """Decode and validate a Keycloak JWT. Raises HTTPException on failure."""
    try:
        jwks = _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=KEYCLOAK_CLIENT_ID,
            options={"verify_exp": True},
        )
        return payload
    except JWTError as exc:
        log.warning("auth_oidc.token_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _require_mfa(payload: dict) -> None:
    """Enforce MFA: token must have 'otp' in amr claim."""
    amr = payload.get("amr", [])
    if "otp" not in amr:
        log.warning("auth_oidc.mfa_required", sub=payload.get("sub"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA (OTP) required",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_roles(payload: dict) -> list[str]:
    """Extract realm roles from Keycloak JWT."""
    return payload.get("realm_access", {}).get("roles", [])


def require_role(role: str):
    """Dependency factory: require a specific role."""

    def _check(payload: dict = Depends(require_auth)) -> dict:
        if role not in get_roles(payload):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return payload

    return _check


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Validate Bearer token and enforce MFA."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    _require_mfa(payload)
    return payload


def check_rate_limit(client_id: str) -> None:
    """Rate limit by client_id: MCP_RATE_LIMIT_RPM requests per minute.
    Raises 429 if exceeded.

    Note: this store is in-memory and not shared across worker processes.
    For multi-replica deployments, replace with a Redis sliding-window counter (F4).
    """
    now = time.time()
    window_start = now - 60.0
    timestamps = [t for t in _rate_limit_store.get(client_id, []) if t > window_start]
    if len(timestamps) >= MCP_RATE_LIMIT_RPM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {MCP_RATE_LIMIT_RPM} requests/minute",
            headers={"Retry-After": "60"},
        )
    timestamps.append(now)
    _rate_limit_store[client_id] = timestamps

    # Evict idle clients to prevent unbounded memory growth.
    # Only run cleanup occasionally (when store grows large) to avoid O(n) on every request.
    if len(_rate_limit_store) > 10_000:
        stale = [k for k, v in _rate_limit_store.items() if not v or v[-1] < window_start]
        for k in stale:
            del _rate_limit_store[k]


def require_reviewer(payload: dict = Depends(require_auth)) -> dict:
    """Shortcut dependency for reviewer role."""
    if "reviewer" not in get_roles(payload) and "admin" not in get_roles(payload):
        raise HTTPException(status_code=403, detail="Reviewer or Admin role required")
    return payload


def require_admin(payload: dict = Depends(require_auth)) -> dict:
    if "admin" not in get_roles(payload):
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload


def check_self_approval(actor_id: str, approver_payload: dict) -> None:
    """Enforce segregation of duties: user cannot approve their own exception."""
    approver_sub = approver_payload.get("sub", "")
    if actor_id == approver_sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval not permitted (segregation of duties)",
        )
