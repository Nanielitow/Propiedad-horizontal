# syntax=docker/dockerfile:1.7
# Imagen única para API (uvicorn), worker y beat (Celery).

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken \
    PATH="/opt/venv/bin:$PATH"

# Dependencias de sistema para OCR (ocrmypdf -> tesseract + ghostscript)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-spa ghostscript \
 && rm -rf /var/lib/apt/lists/*

# Cliente de PostgreSQL 18 (la versión de Neon) para los respaldos diarios: pg_dump y pg_restore
# deben ser de la misma versión del servidor o más nuevos. Repositorio oficial PGDG.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && apt-get purge -y curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.29 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock* ./

# ---------------------------------------------------------------------------
# dev: incluye dependencias de desarrollo; el código llega por bind mount.
# El venv vive en /opt/venv para que el bind mount de /app no lo oculte.
# ---------------------------------------------------------------------------
FROM base AS dev
# Sin cachés de BuildKit (--mount=type=cache): Railway exige un id por servicio y este
# Dockerfile lo comparten api, worker y beat. UV_NO_CACHE evita dejar el caché en la imagen.
RUN UV_NO_CACHE=1 uv sync --no-install-project
# Pre-descarga el tokenizador (tiktoken lo baja de internet en el primer uso)
RUN python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# prod
# ---------------------------------------------------------------------------
FROM base AS prod
RUN UV_NO_CACHE=1 uv sync --no-dev --no-install-project
RUN python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"
COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
