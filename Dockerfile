FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies (layer cached until pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source and install the project itself
COPY src/ src/
RUN uv sync --frozen --no-dev

# config.yml is mounted at runtime: -v ./config.yml:/app/config.yml:ro
CMD ["uv", "run", "--no-sync", "doc-worker"]
