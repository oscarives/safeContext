# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Build context: project root (.) — gives access to apps/workers/ and apps/api/db/
FROM python:3.14-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies (from apps/workers/requirements.txt)
COPY apps/workers/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ADR-010 / E5.3: bake ML models into image at build time
ENV TRANSFORMERS_CACHE=/models/transformers
RUN mkdir -p /models/spacy /models/transformers

RUN python -m spacy download en_core_web_lg && \
    python -c "import spacy; m=spacy.load('en_core_web_lg'); print(m.path)" | \
    xargs -I{} cp -r {} /models/spacy/en_core_web_lg/

RUN python -c "from presidio_analyzer import AnalyzerEngine; AnalyzerEngine()" && \
    echo "Presidio initialized successfully"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

# Layout:
#   /workspace/workers/   ← worker source (from workers/)
#   /workspace/db/        ← SQLAlchemy models (from apps/api/db/)
# PYTHONPATH=/workspace → "from workers.xxx" and "from db.xxx" both resolve
WORKDIR /workspace

COPY --from=builder /usr/local/lib/python3.14/site-packages \
                    /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /models /models

# Copy worker source (destination ./workers/ keeps Python imports as "from workers.xxx")
COPY apps/workers/ ./workers/

# Copy SQLAlchemy models from API (shared schema)
COPY apps/api/db/ ./db/

ENV PYTHONPATH=/workspace
ENV LOCAL_MODELS_PATH=/models/local
ENV TRANSFORMERS_CACHE=/models/transformers
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

RUN useradd -r -u 1001 -g root appuser \
    && chown -R appuser:root /workspace
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import redis; r=redis.from_url('${REDIS_URL:-redis://redis:6379/0}'); r.ping()" || exit 1

CMD ["python", "-m", "dramatiq", "workers.main", "workers.agents", "--processes", "2", "--threads", "4"]
