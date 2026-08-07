FROM ghcr.io/astral-sh/uv:0.12.2 AS uv

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN groupadd --system sensflow \
    && useradd --system --gid sensflow --home-dir /app sensflow

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY migrations ./migrations
COPY sensflow ./sensflow

USER sensflow

CMD ["sh", "-c", "/app/.venv/bin/alembic upgrade head && exec /app/.venv/bin/python -m sensflow"]
