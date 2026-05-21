"""Shared constants for the SafeContext API.

Sentinel values and other constants that would otherwise be copy-pasted
across multiple modules live here. Import from this module — never redefine.
"""

import uuid

# Placeholder actor/reviewer identity used until real OIDC auth is wired (F4).
# Any Operation or Redaction row with this actor_id was created before F4.
# Search for this constant to find all places that need upgrading.
SENTINEL_ACTOR_ID: uuid.UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")
