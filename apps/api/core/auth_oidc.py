"""OIDC authentication middleware for SafeContext API.

Validates JWT tokens issued by Keycloak.
Enforces MFA (verified by amr claim containing 'otp').
Provides role-based access control via JWT realm_access.roles.

JWT library: PyJWT (replaces python-jose which lacked Python 3.14 support).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
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
# deque(maxlen=RPM) gives O(1) append + O(1) head-eviction vs list-rebuild per request.
MCP_RATE_LIMIT_RPM = settings.mcp_rate_limit_rpm
_rate_limit_store: dict[str, deque[float]] = defaultdict(
    lambda: deque(maxlen=MCP_RATE_LIMIT_RPM)
)
_rate_limit_last_eviction: float = 0.0
_RATE_LIMIT_EVICTION_INTERVAL: float = 30.0  # evict stale client entries at most once per 30 s

# ── JWKS cache ────────────────────────────────────────────────────────────────
# Raw dict AND parsed PyJWKSet are cached together so PyJWKSet.from_dict()
# (which constructs RSA key objects) runs once per TTL, not on every request.

_jwks_cache: dict = {}
_jwks_keyset: PyJWKSet | None = None   # parsed key set, avoids re-parsing per request
_jwks_fetched_at: float = 0.0
_jwks_lock = asyncio.Lock()
_JWKS_TTL: float = 900.0   # 15 minutes


async def _get_jwks() -> PyJWKSet:
    """Fetch JWKS from Keycloak, cached with a 15-minute TTL.

    Returns the parsed PyJWKSet (not the raw dict) so callers don't need to
    call PyJWKSet.from_dict() on every token verification — RSA key construction
    is done once per cache refresh cycle.

    Uses asyncio.Lock with double-checked locking to avoid thundering herd.
    """
    global _jwks_cache, _jwks_keyset, _jwks_fetched_at

    now = time.time()
    if _jwks_keyset is not None and now - _jwks_fetched_at < _JWKS_TTL:
        return _jwks_keyset

    async with _jwks_lock:
        now = time.time()
        if _jwks_keyset is not None and now - _jwks_fetched_at < _JWKS_TTL:
            return _jwks_keyset

        url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_keyset = PyJWKSet.from_dict(_jwks_cache)   # parse once
            _jwks_fetched_at = time.time()
            log.debug("auth_oidc.jwks_refreshed")

    return _jwks_keyset  # type: ignore[return-value]


def _decode_with_jwks(token: str, jwks_obj: PyJWKSet) -> dict:
    """Decode a JWT using a cached PyJWKSet with PyJWT.

    Selects the correct signing key by matching the 'kid' claim in the token
    header against the JWKS key set.
    """
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

    # Audience validation is enabled — the safecontext-ui Keycloak client has an
    # oidc-audience-mapper that includes "safecontext-api" in the access token's
    # aud claim. See apps/infra/compose/keycloak/realm-safecontext.json.
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
        jwks_obj = await _get_jwks()
        return _decode_with_jwks(token, jwks_obj)
    except InvalidTokenError as exc:
        log.warning("auth_oidc.token_invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _require_mfa(payload: dict) -> None:
    """Enforce MFA: token must have 'otp' in amr claim.

    Skipped when settings.api_require_mfa is False (dev environments where
    users don't have TOTP configured). Always enforced in production.
    """
    if not settings.api_require_mfa:
        return
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


async def check_rate_limit_redis(client_id: str, redis_client) -> None:
    """Rate limit via Redis sorted sets — works across multiple API replicas.

    Pattern: ZREMRANGEBYSCORE (evict expired) + ZCARD (count) + ZADD (add current)
    in a single pipeline → atomic O(log n) sliding window.
    """
    now = time.time()
    window_start = now - 60.0
    key = f"sc:rl:{client_id}"

    async with redis_client.pipeline(transaction=True) as pipe:
        await pipe.zremrangebyscore(key, 0, window_start)
        await pipe.zcard(key)
        await pipe.zadd(key, {str(now): now})
        await pipe.expire(key, 120)   # TTL safety net
        results = await pipe.execute()

    count_before = results[1]
    if count_before >= MCP_RATE_LIMIT_RPM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {MCP_RATE_LIMIT_RPM} requests/minute",
            headers={"Retry-After": "60"},
        )


_rate_limit_fallback_warned = False


def check_rate_limit(client_id: str) -> None:
    """Rate limit by client_id: MCP_RATE_LIMIT_RPM requests per minute.

    Fallback in-memory implementation used when Redis is unavailable.

    Uses deque(maxlen=RPM) for O(1) append + O(1) head-eviction instead of
    rebuilding a filtered list on every request.

    WARNING: in-memory, not shared across worker processes.
    With workers>1 the effective limit is RPM × num_workers.
    """
    global _rate_limit_fallback_warned
    if not _rate_limit_fallback_warned:
        log.warning(
            "rate_limit.fallback_active",
            detail="Using in-memory rate limiter — limit is per-worker, not global",
        )
        _rate_limit_fallback_warned = True
    global _rate_limit_last_eviction

    now = time.time()
    window_start = now - 60.0
    dq = _rate_limit_store[client_id]

    # Evict expired timestamps from the front (deque is ordered oldest→newest)
    while dq and dq[0] <= window_start:
        dq.popleft()

    if len(dq) >= MCP_RATE_LIMIT_RPM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {MCP_RATE_LIMIT_RPM} requests/minute",
            headers={"Retry-After": "60"},
        )
    dq.append(now)  # deque mutates in-place; no reassignment needed

    # Evict idle client entries at most once per 30 s to bound memory.
    if len(_rate_limit_store) > 10_000 and now - _rate_limit_last_eviction > _RATE_LIMIT_EVICTION_INTERVAL:
        stale = [k for k, v in _rate_limit_store.items() if not v or v[-1] < window_start]
        for k in stale:
            del _rate_limit_store[k]
        _rate_limit_last_eviction = now


async def require_reviewer(payload: dict = Depends(require_auth)) -> dict:
    """Shortcut dependency for reviewer or admin role."""
    roles = get_roles(payload)  # bind once — avoid calling get_roles() twice
    if "reviewer" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or Admin role required",
        )
    return payload


async def require_admin(payload: dict = Depends(require_auth)) -> dict:
    """Shortcut dependency for admin role."""
    if "admin" not in get_roles(payload):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return payload


def check_self_approval(actor_id: str, approver_payload: dict) -> None:
    """Enforce segregation of duties: user cannot approve their own exception."""
    approver_sub = approver_payload.get("sub", "")
    if actor_id == approver_sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval not permitted (segregation of duties)",
        )
