from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://redis:6379/0"
    broker_adapter: str = "redis"
    storage_adapter: str = "minio"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_artifacts: str = "safecontext-artifacts"
    minio_use_ssl: bool = False

    opa_url: str = "http://opa:8181"
    opa_policy_path: str = "/v1/data/safecontext"

    api_secret_key: str
    api_debug: bool = False
    # Set to False in dev when users don't have TOTP configured (realm-safecontext.dev.json).
    # MUST be True in production — enforces MFA on every authenticated API call.
    api_require_mfa: bool = True

    mcp_auth_token: str = ""
    mcp_rate_limit_rpm: int = 100
    safecontext_env: str = "production"  # "dev" | "production"

    # OIDC / Keycloak
    keycloak_url: str = "http://keycloak:8080"
    keycloak_realm: str = "safecontext"
    keycloak_client_id: str = "safecontext-api"

    # Vault KMS
    vault_addr: str = "http://vault:8200"
    vault_dev_token: str = "safecontext-dev-token"
    vault_transit_key: str = "safecontext-signing"  # Transit engine key name

    # TSA (RFC 3161) — Timestamp Authority for audit evidence non-repudiation
    tsa_url: str = "https://freetsa.org/tsr"
    tsa_enabled: bool = True  # Set False to skip TSA in dev/air-gapped

    http_client_timeout: float = 5.0

    # PostgreSQL connection pool tuning
    db_pool_size: int = 10             # Persistent connections per worker
    db_pool_max_overflow: int = 20     # Burst connections above pool_size
    db_pool_recycle: int = 1800        # Recycle connections after 30 min
    db_pool_timeout: float = 10.0      # Fail fast if no connection in 10s

    otel_exporter_otlp_endpoint: str = "http://otel:4317"
    otel_service_name: str = "safecontext-api"


settings = Settings()
