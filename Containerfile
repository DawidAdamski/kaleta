FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini* ./

# Expose default port
EXPOSE 8080

# Run the application
CMD ["uv", "run", "kaleta"]
