"""Root conftest.py — set required environment variables before any import."""

import os

# Minimal env vars required by Settings() to avoid ValidationError in tests
_TEST_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "MINIO_ACCESS_KEY": "test-access-key",
    "MINIO_SECRET_KEY": "test-secret-key",
    "API_SECRET_KEY": "test-secret-key-for-audit-hmac-32chars",
    "MCP_AUTH_TOKEN": "test-mcp-token",
    "REDIS_URL": "redis://localhost:6379/0",
    "OPA_URL": "http://localhost:8181",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
    "OTEL_SERVICE_NAME": "safecontext-test",
    "NEXTAUTH_SECRET": "test-nextauth-secret",
    "NEXTAUTH_URL": "http://localhost:3000",
    "KEYCLOAK_URL": "http://localhost:8080",
    "VAULT_ADDR": "http://localhost:8200",
    "VAULT_DEV_TOKEN": "test-vault-token",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
