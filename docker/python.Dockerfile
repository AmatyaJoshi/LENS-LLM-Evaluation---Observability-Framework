# Shared image for the Lens API and worker (uv workspace).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependency layer: workspace manifests only.
COPY pyproject.toml uv.lock .python-version ./
COPY packages/lens-core/pyproject.toml packages/lens-core/pyproject.toml
COPY packages/lens-sdk-python/pyproject.toml packages/lens-sdk-python/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY examples/rag_demo/pyproject.toml examples/rag_demo/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages --no-install-workspace

# Source layer.
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY examples/rag_demo ./examples/rag_demo
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

EXPOSE 8000
CMD ["uvicorn", "lens_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
