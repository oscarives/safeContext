from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

_bearer = HTTPBearer(auto_error=False)


def require_mcp_token(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    if credentials is None or credentials.credentials != settings.mcp_auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing MCP token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
