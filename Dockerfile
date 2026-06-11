FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --no-dev --no-editable

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PROMPTCLOAK_HOST=0.0.0.0 \
    PROMPTCLOAK_PORT=8000

WORKDIR /app
COPY --from=builder /app /app
EXPOSE 8000
CMD ["promptcloak", "serve", "--host", "0.0.0.0", "--port", "8000"]
