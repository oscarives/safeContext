from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from adapters.redis_broker import RedisBrokerAdapter
from api.v1 import health as health_module
from api.v1.router import v1_router
from config import settings
from core.logging import get_logger, setup_logging
from core.tracing import setup_tracing
from mcp.router import router as mcp_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # --- startup ---
    setup_logging(debug=settings.api_debug)
    setup_tracing(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )

    broker = RedisBrokerAdapter(url=settings.redis_url)
    try:
        await broker.connect()
    except Exception as exc:
        logger.warning("lifespan.broker.connect_failed", error=str(exc))
    app.state.broker = broker

    # Shared HTTP client for outbound calls (OPA, Keycloak, etc.).
    # Reusing one AsyncClient avoids creating a new TCP connection per request.
    app.state.http_client = httpx.AsyncClient(timeout=5.0)

    logger.info("safecontext_api.started", service=settings.otel_service_name)

    yield

    # --- shutdown ---
    await app.state.http_client.aclose()
    await broker.disconnect()
    logger.info("safecontext_api.stopped")


app = FastAPI(
    title="SafeContext API",
    version="0.1.0",
    description=(
        "Privacy-preserving document scanning API. "
        "Detects PII / sensitive data and enforces OPA-based redaction policies."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# API routers
app.include_router(v1_router, prefix="/v1")

# MCP Server — exposes SafeContext agents as MCP tools
app.include_router(mcp_router)

# /health is mounted at root (no /v1 prefix) for Docker/k8s healthchecks
app.include_router(health_module.router)
