FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace-level files — rarely change, maximise layer caching
COPY pyproject.toml uv.lock ./

# Workspace member manifests (uv needs them for resolution)
COPY shared/ ./shared/
COPY llm-gateway/pyproject.toml ./llm-gateway/pyproject.toml
COPY evaluation/pyproject.toml ./evaluation/pyproject.toml
COPY observability/pyproject.toml ./observability/pyproject.toml

# Install runtime deps for this service (from locked versions, no dev extras)
RUN uv sync --frozen --package llm-gateway --no-dev --no-install-project

# Copy service source (invalidates only this layer on code changes)
COPY llm-gateway/ .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app:/app/shared/src

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
