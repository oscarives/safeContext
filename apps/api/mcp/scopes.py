"""MCP scope definitions and enforcement."""
from __future__ import annotations

from fastapi import HTTPException


TOOL_SCOPES: dict[str, str] = {
    "safecontext.scan": "mcp:scan",
    "safecontext.sanitize": "mcp:sanitize",
    "safecontext.classify": "mcp:classify",
    "safecontext.audit": "mcp:audit",
    "safecontext.policy.get": "mcp:policy",
    "safecontext.approve": "mcp:approve",
}


def require_tool_scope(tool_name: str, token_payload: dict) -> None:
    """Raise 403 HTTPException if the token lacks the required scope for tool_name.

    The scope claim is expected as a space-separated string (standard OAuth 2.0/2.1
    format). Unknown tool names are allowed through — the router handles 404.
    """
    required = TOOL_SCOPES.get(tool_name)
    if required is None:
        return  # unknown tool — let router handle it

    granted = set(token_payload.get("scope", "").split())
    if required not in granted:
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient scope. Required: {required}",
        )
