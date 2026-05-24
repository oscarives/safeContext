"""Shared constants for the SafeContext API.

Sentinel values and other constants that would otherwise be copy-pasted
across multiple modules live here. Import from this module — never redefine.
"""

import uuid

# Placeholder actor/reviewer identity used until real OIDC auth is wired (F4).
# Any Operation or Redaction row with this actor_id was created before F4.
# Search for this constant to find all places that need upgrading.
SENTINEL_ACTOR_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Default tenant for pre-F6 data and single-tenant deployments.
# Migration 0008 creates this tenant and backfills all existing rows.
DEFAULT_TENANT_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")
DEFAULT_TENANT_SLUG: str = "default"

# ── Timeouts (seconds) ──────────────────────────────────────────────────────
HEALTH_CHECK_TIMEOUT: float = 2.0          # Redis/MinIO health check socket timeout
HTTP_CLIENT_TIMEOUT_DEFAULT: float = 5.0   # Default httpx.AsyncClient timeout
DB_POOL_TIMEOUT: float = 10.0              # SQLAlchemy pool checkout timeout

# ── Limits ───────────────────────────────────────────────────────────────────
DOCUMENT_MAX_LENGTH: int = 10_485_760      # 10 MB max document size
REVIEW_PAGE_LIMIT_DEFAULT: int = 20        # Default pagination page size
REVIEW_PAGE_LIMIT_MAX: int = 100           # Max pagination page size
MCP_RATE_LIMIT_RPM_DEFAULT: int = 100      # Default MCP rate limit (requests/min)

# ── Policy ───────────────────────────────────────────────────────────────────
FALLBACK_POLICY_VERSION: str = "1.0.0"     # Used when OPA is unreachable
