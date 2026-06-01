FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Install dependencies (layer cached until pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY src/doc_worker/ /app/

# config.yml is mounted at runtime: -v ./config.yml:/app/config.yml:ro
WORKDIR /app
ENV PYTHONPATH=/build/.venv/lib/python3.13/site-packages
CMD ["/build/.venv/bin/python", "/app/main.py"]
