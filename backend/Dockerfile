# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract OCR with English + Hindi language packs for document digitisation.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS deps
COPY requirements.txt .
# Cache mount: wheels are reused across rebuilds instead of re-downloaded (~250 MB of
# scipy/scikit-learn/grpcio). The cache never becomes part of a layer.
RUN --mount=type=cache,id=pip,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.txt

FROM base AS runtime
COPY --from=deps /install /usr/local
RUN groupadd --system --gid 10001 cmg && useradd --system --uid 10001 --gid cmg --home /app cmg
COPY --chown=cmg:cmg alembic.ini ./
COPY --chown=cmg:cmg migrations ./migrations
COPY --chown=cmg:cmg app ./app
USER cmg
# 8000 = HTTP API, 9464 = Temporal worker metrics, 9465 = consumer metrics.
# No HEALTHCHECK here on purpose: this one image also runs the migrate job, the Temporal
# worker and the Kafka consumers, none of which serve HTTP on 8000. Each compose service
# declares the probe that is right for it.
EXPOSE 8000 9464 9465
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000"]
