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

# ADR-010 / E5.3: Download and bake ML models into image at build time.
# Models are NEVER downloaded at runtime — this guarantees air-gapped operation.
ENV TRANSFORMERS_CACHE=/models/transformers
RUN mkdir -p /models/spacy /models/transformers

# spaCy model — download via pip then copy to /models for deterministic path resolution
RUN python -m spacy download en_core_web_lg && \
    python -c "import spacy; m=spacy.load('en_core_web_lg'); print(m.path)" | \
    xargs -I{} cp -r {} /models/spacy/en_core_web_lg/

# Presidio models (uses spaCy internally — already downloaded above)
RUN python -c "from presidio_analyzer import AnalyzerEngine; AnalyzerEngine()" && \
    echo "Presidio initialized successfully"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages

# Copy installed binaries (dramatiq CLI, etc.) from builder
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy baked-in ML models from builder (ADR-010 / E5.3: air-gapped operation)
COPY --from=builder /models /models

# Copy application source
COPY . .

# Non-root user for security (principle of least privilege)
RUN useradd -r -u 1001 -g root appuser \
    && chown -R appuser:root /app

USER appuser

# E5.3: point model_loader to the image-baked path; disable HuggingFace downloads
ENV LOCAL_MODELS_PATH=/models/local
ENV TRANSFORMERS_CACHE=/models/transformers
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

# Healthcheck: verify broker connectivity every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import redis; r=redis.from_url('${REDIS_URL:-redis://redis:6379/0}'); r.ping()" || exit 1

# Start Dramatiq worker process
# --processes: one process per CPU core for parallelism
# --threads:   async tasks per process (IO-bound detection workloads)
CMD ["python", "-m", "dramatiq", "workers.agents", "--processes", "2", "--threads", "4"]
