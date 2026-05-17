# TODO: Replace placeholder with real application code when workers/ is implemented.
# This multi-stage Dockerfile is structurally correct and ready for development.

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY requirements*.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt 2>/dev/null || \
    pip install --no-cache-dir --prefix=/install dramatiq[redis] 2>/dev/null || true

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Non-root user for security
RUN useradd -r -u 1001 -g root appuser && chown -R appuser:root /app
USER appuser

# TODO: Replace with actual entrypoint once workers/ Dramatiq app is scaffolded
CMD ["python", "-m", "dramatiq", "workers.main"]
