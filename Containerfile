FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* README.md ./

# Slim image — runtime deps only (excludes [dependency-groups] dev)
RUN uv sync --frozen --no-dev --no-install-project

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
    uv sync --frozen --no-dev

# `uv run` would otherwise sync the dev group into the image at every start.
ENV UV_NO_SYNC=1

EXPOSE 8080

CMD ["uv", "run", "kaleta"]
