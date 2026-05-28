"""workers/config.py — Centralised settings for all SafeContext workers.

Mirrors apps/api/config.py but scoped to the worker process.
All environment variable access in workers must go through this module —
never call os.environ.get() directly inside agents or core modules.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str

    # ── Redis (broker) ────────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── OPA ───────────────────────────────────────────────────────────────────
    opa_url: str = "http://opa:8181"
    policy_poll_interval: int = 30  # seconds between OPA hot-reload polls

    # ── MinIO / Storage ───────────────────────────────────────────────────────
    minio_endpoint: str = "minio:9000"
    minio_access_key: str        # required — no default, fails fast at startup if missing
    minio_secret_key: str        # required — matches api/config.py convention
    minio_bucket_artifacts: str = "safecontext-artifacts"
    minio_use_ssl: bool = False

    # ── Outbox relay ──────────────────────────────────────────────────────────
    outbox_poll_interval: float = 1.0   # seconds between outbox polls
    outbox_batch_size: int = 10         # max events per relay batch

    # ── Vault Transit — write-time evidence signing (F7-5, ADR-014/H1) ─────────
    # The auditor_agent seals each completed operation with the asymmetric key
    # the moment it finishes. When audit_sign_on_write is False (air-gapped /
    # no Vault) only the chain hash is written; the signature stays NULL and the
    # read-time export can still enforce audit_require_digital_signature.
    vault_addr: str = "http://vault:8200"
    vault_dev_token: str = "safecontext-dev-token"
    vault_transit_key: str = "safecontext-signing"
    audit_sign_on_write: bool = True

    # ── Worker runtime ────────────────────────────────────────────────────────
    worker_concurrency: int = 4
    worker_max_retries: int = 3
    detector_confidence_threshold: float = 0.85

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("outbox_batch_size")
    @classmethod
    def validate_batch_size(cls, v: int) -> int:
        if v < 1 or v > 1000:
            raise ValueError("outbox_batch_size must be between 1 and 1000")
        return v

    @field_validator("policy_poll_interval")
    @classmethod
    def validate_poll_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError("policy_poll_interval must be >= 1 second")
        return v

    @field_validator("outbox_poll_interval")
    @classmethod
    def validate_outbox_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("outbox_poll_interval must be > 0 seconds")
        return v


settings = WorkerSettings()
