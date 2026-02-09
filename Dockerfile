FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application code
COPY . .
RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "fastapi_k8s:app", "--host", "0.0.0.0", "--port", "8000"]
