# syntax=docker/dockerfile:1.7
# Server image (docs/specs/07-environments.md, section 7.1). Build context: repository root.
#   base    — Python, uv and runtime dependencies in /opt/venv
#   dev     — base + development dependencies; code is mounted from the host (deploy/dev)
#   runtime — fresh slim image with /opt/venv and the code; no uv, no compilers

ARG PYTHON_IMAGE=python:3.13-slim
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.32

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/opt/venv/bin:$PATH
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app/server
COPY server/pyproject.toml server/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM base AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=almi_license.settings.prod
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=base /opt/venv /opt/venv
WORKDIR /app/server
COPY server/ ./
USER app
# Entry points api/worker/migrate (Gunicorn + Uvicorn) and OCI labels come with E15-01.
ENTRYPOINT ["python", "manage.py"]
CMD ["check", "--deploy"]
