# Talk To Your Data v2: one container, no external services (docs/DESIGN.md, Hosting).
# Layer order is chosen so that editing app code never re-downloads the model:
#   dependencies -> embedding model -> app + data -> preloaded index.
FROM python:3.12-slim

# uv from its official image (DESIGN.md); the version is whatever :latest is at build time.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_SYNC=1 \
    FASTEMBED_CACHE_PATH=/app/.fastembed \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies only: tool.uv.package = false, so there is no project to install.
# --no-cache keeps uv's wheel cache out of the layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

# Unprivileged runtime user. /app is writable so preload can create data/index.db
# and the app can write session uploads into it; the venv stays root-owned, read-only.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p /app/.fastembed \
    && chown app:app /app /app/.fastembed
USER app

# Bake the embedding model so a cold start never downloads anything.
RUN uv run python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

# Runtime files only; .dockerignore keeps .git, .venv, tests, docs and the local index out.
COPY --chown=app:app app/ app/
COPY --chown=app:app data/ data/
COPY --chown=app:app eval/ eval/
COPY --chown=app:app README.md LICENSE ./

# Build data/index.db from data/preloaded at build time so the container serves at once.
RUN uv run python -m app.ingestion.preload

# The model is already in /app/.fastembed: never reach for the network at startup.
ENV HF_HUB_OFFLINE=1

EXPOSE 8000
# Render injects PORT; anything else gets 8000.
CMD ["sh", "-c", "exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
