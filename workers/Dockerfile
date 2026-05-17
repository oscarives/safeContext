# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (needed for asyncpg, some spaCy wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy only the dependency manifest first (layer-cache optimisation)
COPY pyproject.toml .

# Install all dependencies into the system site-packages
RUN uv pip install --system --no-cache .

# ADR-010: Download and install spaCy model at build time — never at runtime.
# Using en_core_web_lg for best recall on PII/entity recognition.
RUN python -m spacy download en_core_web_lg

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages

# Copy installed binaries (dramatiq CLI, etc.) from builder
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Non-root user for security (principle of least privilege)
RUN useradd -r -u 1001 -g root appuser \
    && chown -R appuser:root /app

USER appuser

# Healthcheck: verify broker connectivity every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import redis; r=redis.from_url('${REDIS_URL:-redis://redis:6379/0}'); r.ping()" || exit 1

# Start Dramatiq worker process
# --processes: one process per CPU core for parallelism
# --threads:   async tasks per process (IO-bound detection workloads)
CMD ["python", "-m", "dramatiq", "workers.agents", "--processes", "2", "--threads", "4"]
