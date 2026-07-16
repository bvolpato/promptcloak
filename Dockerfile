FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --no-dev --no-editable --locked

FROM python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28

ENV PATH="/app/.venv/bin:$PATH" \
    PROMPTCLOAK_HOST=0.0.0.0 \
    PROMPTCLOAK_PORT=8000

WORKDIR /app
RUN groupadd --gid 10001 promptcloak \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin promptcloak
COPY --from=builder --chown=promptcloak:promptcloak /app /app
USER 10001:10001
EXPOSE 8000
CMD ["promptcloak", "serve", "--host", "0.0.0.0", "--port", "8000"]
