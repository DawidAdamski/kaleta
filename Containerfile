FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* README.md ./

# Runtime deps only (excludes [dependency-groups] dev). The `forecast` extra
# ships Prophet so account-balance forecasting works out of the box instead of
# falling back to the naive projection (is_prophet_available() -> False).
RUN uv sync --frozen --no-dev --extra forecast --no-install-project

# Copy application code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini ./
# The tenant registry's migrations (every instance keeps a `public` registry).
COPY alembic_public/ alembic_public/
COPY alembic_public.ini ./

# The project itself, now that its code is in place. The image has no .git, so
# hatch-vcs can't read the version from git — the CI build passes it in as
# KALETA_VERSION (auto-versioning Part 2); a local build without it falls back to
# 0.0.0, matching pyproject's fallback-version.
ARG KALETA_VERSION=""
RUN SETUPTOOLS_SCM_PRETEND_VERSION="${KALETA_VERSION:-0.0.0}" \
    uv sync --frozen --no-dev --extra forecast

# `uv run` would otherwise sync the dev group into the image at every start.
ENV UV_NO_SYNC=1

# Run as a non-root user (Trivy DS-0002 / assessment F-6). The code and the
# .venv were built as root; hand /app to the runtime user and drop to it.
# An explicit HOME keeps NiceGUI's file-backed sessions under /home/app/.kaleta.
# Pre-create that dir owned by the user so a Compose named volume mounted there
# initialises app-owned (Compose has no fsGroup; k3s uses fsGroup instead).
RUN useradd --create-home --uid 10001 --user-group app \
    && mkdir -p /home/app/.kaleta \
    && chown -R app:app /app /home/app
ENV HOME=/home/app
USER app

EXPOSE 8080

CMD ["uv", "run", "kaleta"]
