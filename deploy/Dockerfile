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
    DJANGO_SETTINGS_MODULE=almi_license.settings.prod \
    HOME=/tmp
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=base /opt/venv /opt/venv
WORKDIR /app/server
COPY server/ ./
COPY --chmod=0755 deploy/entrypoint.sh /usr/local/bin/almi-entrypoint
# The key of a local server (LOCAL_SERVER_KEY_FILE) lives in a named volume here: an empty volume
# takes the owner of this directory, so the first-run wizard can write the key as app.
RUN install -d -o app -g app -m 0700 /var/lib/almi
ARG APP_VERSION=0.1.0
ENV APP_VERSION=${APP_VERSION}
LABEL org.opencontainers.image.title="almi-license" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.description="ALMI licensing server (central and local modes)"
USER app
EXPOSE 8000
ENTRYPOINT ["almi-entrypoint"]
CMD ["api"]
