import boto3
import redis.asyncio as aioredis
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter
from sqlalchemy import text

from config import settings
from core.logging import get_logger
from db.session import AsyncSessionLocal
from schemas.health import HealthResponse

router = APIRouter()
logger = get_logger(__name__)


async def _check_postgres() -> str:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("health.postgres.error", error=str(exc))
        return "error"


async def _check_redis() -> str:
    client: aioredis.Redis | None = None  # type: ignore[type-arg]
    try:
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await client.ping()
        return "ok"
    except Exception as exc:
        logger.warning("health.redis.error", error=str(exc))
        return "error"
    finally:
        if client is not None:
            await client.aclose()


def _check_minio() -> str:
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=(
                f"{'https' if settings.minio_use_ssl else 'http'}://{settings.minio_endpoint}"
            ),
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        )
        s3.head_bucket(Bucket=settings.minio_bucket_artifacts)
        return "ok"
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        # 404 means bucket doesn't exist yet, but MinIO is reachable
        if code == "404":
            return "ok"
        logger.warning("health.minio.client_error", code=code)
        return "error"
    except (BotoCoreError, Exception) as exc:
        logger.warning("health.minio.error", error=str(exc))
        return "error"


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Return liveness + dependency status. Always HTTP 200 (Docker-compatible)."""
    pg = await _check_postgres()
    rd = await _check_redis()
    mn = _check_minio()

    overall = "ok" if pg == "ok" and rd == "ok" and mn == "ok" else "degraded"
    return HealthResponse(
        status=overall,  # type: ignore[arg-type]
        postgres=pg,  # type: ignore[arg-type]
        redis=rd,  # type: ignore[arg-type]
        minio=mn,  # type: ignore[arg-type]
    )
