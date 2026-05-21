"""workers/config.py — Centralised settings for all SafeContext workers.

Mirrors apps/api/config.py but scoped to the worker process.
All environment variable access in workers must go through this module —
never call os.environ.get() directly inside agents or core modules.
"""

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
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket_artifacts: str = "safecontext-artifacts"
    minio_use_ssl: bool = False

    # ── Outbox relay ──────────────────────────────────────────────────────────
    outbox_poll_interval: float = 1.0   # seconds between outbox polls
    outbox_batch_size: int = 10         # max events per relay batch

    # ── Worker runtime ────────────────────────────────────────────────────────
    worker_concurrency: int = 4
    worker_max_retries: int = 3
    detector_confidence_threshold: float = 0.85


settings = WorkerSettings()
