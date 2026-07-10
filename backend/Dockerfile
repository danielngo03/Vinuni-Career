# VinUni Career Platform — backend (FastAPI) image for Cloud Run.
#
# Build (from backend/):        docker build -t vinuni-career-api .
# Build with OCR (Tesseract):   docker build --build-arg INSTALL_OCR=true -t vinuni-career-api .
#
# The same image serves three Cloud Run workloads (see docs/DEPLOYMENT_GCP.md):
#   API service:     default CMD (uvicorn, honors Cloud Run's $PORT)
#   Migration job:   command = alembic, args = upgrade head
#   Scheduler:       command = python, args = -m app.worker  (+ BACKGROUND_WORKER_MODE=scheduler)

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

ARG INSTALL_OCR=false

# Install dependencies first so source edits don't invalidate the layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_OCR" = "true" ]; then \
        uv sync --frozen --no-dev --extra ai-production; \
    else \
        uv sync --frozen --no-dev; \
    fi


FROM python:3.12-slim-bookworm

ARG INSTALL_OCR=false

# curl: container healthchecks. Tesseract + poppler only for the OCR profile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && if [ "$INSTALL_OCR" = "true" ]; then \
        apt-get install -y --no-install-recommends \
            tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng poppler-utils; \
    fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1001 appuser \
    && mkdir -p /app/.dev/storage \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Shell form so Cloud Run's injected $PORT is honored; exec keeps uvicorn as PID 1.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
