# Testing

Run from repository root. Never use real credentials in tests or logs.

```bash
uv sync --extra dev --locked
uv run scripts/check_release.py
uv run scripts/audit_secrets.py
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run --with pip-audit pip-audit
uv build
helm lint ./charts/promptcloak
helm template promptcloak ./charts/promptcloak >/dev/null
docker build -t promptcloak:release-check .
docker run --rm --entrypoint promptcloak promptcloak:release-check version
```

Before release, also run checks under Python 3.12 and 3.13:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/promptcloak-py312 uv sync --python 3.12 --extra dev --locked
UV_PROJECT_ENVIRONMENT=/tmp/promptcloak-py312 uv run pytest
UV_PROJECT_ENVIRONMENT=/tmp/promptcloak-py313 uv sync --python 3.13 --extra dev --locked
UV_PROJECT_ENVIRONMENT=/tmp/promptcloak-py313 uv run pytest
```
