# Build context: repo root (see docker-compose.yml).
FROM python:3.15-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keep the venv outside the source tree so a bind-mounted checkout never clobbers it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/services/api
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-install-project

COPY db/seed /app/db/seed
COPY db/0001_initial.sql /app/db/0001_initial.sql
COPY services/api /app/services/api

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
