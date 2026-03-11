FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install to /opt/ouroboros so the /app:ro volume mount doesn't shadow the venv
WORKDIR /opt/ouroboros

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install Playwright browser for UI validation
RUN /opt/ouroboros/.venv/bin/python -m playwright install chromium --with-deps

# Copy application code
COPY agents/ agents/

# curl required for healthcheck in docker-compose
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

CMD ["/opt/ouroboros/.venv/bin/python", "-m", "agents.server"]
