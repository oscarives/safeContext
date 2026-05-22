"""Root conftest for worker tests — seed required env vars before any import.

WorkerSettings (pydantic-settings) is instantiated at module level in
workers/config.py. If DATABASE_URL or other required vars are missing when
a worker module is first imported, pydantic raises ValidationError and the
test suite fails before any test runs. This conftest seeds safe test defaults
so the import succeeds.

Mirrors apps/api/conftest.py — keep in sync when adding new required fields.
"""

import os

_TEST_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "OPA_URL": "http://localhost:8181",
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ACCESS_KEY": "test-access-key",
    "MINIO_SECRET_KEY": "test-secret-key",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
