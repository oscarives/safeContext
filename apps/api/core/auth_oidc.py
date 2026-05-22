"""OIDC authentication middleware for SafeContext API.

Validates JWT tokens issued by Keycloak.
Enforces MFA (verified by amr claim containing 'otp').
Provides role-based access control via JWT realm_access.roles.

JWT library: PyJWT (replaces python-jose which lacked Python 3.14 support).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Annotated

import httpx
import jwt as pyjwt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKSet

from config import settings

log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)

KEYCLOAK_URL = settings.keycloak_url
KEYCLOAK_REALM = settings.keycloak_realm
KEYCLOAK_CLIENT_ID = settings.keycloak_client_id

# Rate limiting state (per client_id, in-memory for single instance; Redis in F4 HA)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
MCP_RATE_LIMIT_RPM = settings.mcp_rate_limit_rpm

# ── JWKS cache ────────────────────────────────────────────────────────────────

_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_jwks_lock = asyncio.Lock()
_JWKS_TTL: float = 900.0   # 15 minutes


async def _get_jwks() -> dict:
    """Fetch JWKS from Keycloak, cached with a 15-minute TTL.

    Uses asyncio.Lock with double-checked locking to avoid thundering herd.
    """
    global _jwks_cache, _jwks_fetched_at

    now = time.time()
    if _jwks_cache and now - _jwks_fetched_at < _JWKS_TTL:
        return _jwks_cache

    async with _jwks_lock:
        now = time.time()
        if _jwks_cache and now - _jwks_fetched_at < _JWKS_TTL:
            return _jwks_cache

        url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = time.time()
            log.debug("auth_oidc.jwks_refreshed")

    return _jwks_cache


def _decode_with_jwks(token: str, jwks_dict: dict) -> dict:
    """Decode a JWT using a cached JWKS dict with PyJWT.

    Selects the correct signing key by matching the 'kid' claim in the token
    header against the JWKS key set.
    """
    jwks_obj = PyJWKSet.from_dict(jwks_dict)

    # Match signing key by kid (key ID) from the token header
    header = pyjwt.get_unverified_header(token)
    kid = header.get("kid")
    if kid:
        signing_key = next(
            (k for k in jwks_obj.keys if k.key_id == kid),
            None,
        )
    else:
        signing_key = jwks_obj.keys[0] if jwks_obj.keys else None

    if signing_key is None:
        raise InvalidTokenError("No matching signing key found in JWKS")

    return pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=KEYCLOAK_CLIENT_ID,
        options={"verify_exp": True},
    )


async def _decode_token(token: str) -> dict:
    """Decode and validate a Keycloak JWT. Raises HTTPException on failure."""
    try:
        jwks = await _get_jwks()
        return _decode_with_jwks(token, jwks)
    except InvalidTokenError as exc:
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

    async def _check(payload: dict = Depends(require_auth)) -> dict:
        if role not in get_roles(payload):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return payload

    return _check


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Validate Bearer token and enforce MFA."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = await _decode_token(credentials.credentials)
    _require_mfa(payload)
    return payload


def check_rate_limit(client_id: str) -> None:
    """Rate limit by client_id: MCP_RATE_LIMIT_RPM requests per minute.

    Note: in-memory, not shared across worker processes.
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

    if len(_rate_limit_store) > 10_000:
        stale = [k for k, v in _rate_limit_store.items() if not v or v[-1] < window_start]
        for k in stale:
            del _rate_limit_store[k]


async def require_reviewer(payload: dict = Depends(require_auth)) -> dict:
    """Shortcut dependency for reviewer role."""
    if "reviewer" not in get_roles(payload) and "admin" not in get_roles(payload):
        raise HTTPException(status_code=403, detail="Reviewer or Admin role required")
    return payload


async def require_admin(payload: dict = Depends(require_auth)) -> dict:
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
