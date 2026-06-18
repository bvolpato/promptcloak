FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --no-dev --no-editable --frozen

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PROMPTCLOAK_HOST=0.0.0.0 \
    PROMPTCLOAK_PORT=8000

WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin promptcloak
COPY --from=builder --chown=promptcloak:promptcloak /app /app
USER promptcloak
EXPOSE 8000
CMD ["promptcloak", "serve", "--host", "0.0.0.0", "--port", "8000"]
