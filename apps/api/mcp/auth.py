"""MCP authentication — OAuth 2.1 JWT validation with Keycloak.

In dev mode (SAFECONTEXT_ENV=dev), the legacy static token is accepted
for backward compatibility with local development workflows.
"""
from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.auth_oidc import _decode_token  # reutiliza JWKS validation existente
from config import settings

_bearer = HTTPBearer(auto_error=False)


async def require_mcp_oauth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> dict:
    """Validate OAuth 2.1 JWT from Keycloak for MCP requests.

    Returns the decoded JWT payload dict including sub, scope, client_id, etc.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = credentials.credentials

    # Dev mode: accept legacy static token for local development
    if getattr(settings, "safecontext_env", "production") == "dev":
        static = getattr(settings, "mcp_auth_token", "")
        if static and token == static:
            return {
                "sub": "dev-agent",
                "scope": "mcp:scan mcp:sanitize mcp:classify mcp:audit mcp:policy mcp:approve",
                "client_id": "dev",
                "_raw_token": token,
            }

    # Production: validate JWT from Keycloak
    try:
        payload = await _decode_token(token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid MCP token: {exc}") from exc

    # Verify audience
    aud = payload.get("aud", [])
    if isinstance(aud, str):
        aud = [aud]
    if "safecontext-api" not in aud:
        raise HTTPException(status_code=401, detail="Token audience mismatch")

    return payload


# Alias for any existing imports
require_mcp_token = require_mcp_oauth
