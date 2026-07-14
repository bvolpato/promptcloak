# Contributing

PromptCloak is local-first security software. Keep changes small, tested, and explicit about privacy impact.

## Setup

```bash
uv sync --extra dev
uv run promptcloak doctor
```

## Checks

```bash
uv run scripts/audit_secrets.py
uv run ruff check .
uv run pytest
uv build
```

## Release

Release tags create GitHub releases through `.github/workflows/release.yml`.

```bash
VERSION=0.1.7
uv run scripts/check_release.py --tag "v${VERSION}"
uv run scripts/audit_secrets.py
uv run ruff check .
uv run pytest
uv build
git tag -s "v${VERSION}" -m "PromptCloak ${VERSION}"
git push origin main "v${VERSION}"
```

Before tagging, keep these versions identical:

- `pyproject.toml`
- `src/promptcloak/version.py`
- `charts/promptcloak/Chart.yaml`
- `charts/promptcloak/values.yaml`
- `uv.lock`

The release workflow reruns checks, builds source/wheel/Helm artifacts, writes `SHA256SUMS`,
attests build provenance, publishes an SBOM-backed container image, and uploads release assets.

If a downstream publishing step fails after release creation, fix workflow on `main` and rerun
existing immutable tag:

```bash
gh workflow run release.yml --ref main -f tag="v${VERSION}"
```

## Secret hygiene

- Do not put real secrets, customer prompts, credentials, or private config in issues, tests, docs, commits, or screenshots.
- Use split fixture strings like `"sk-" + "FixtureToken..."` when tests need provider-shaped values.
- Prefer full masking in examples: `[REDACTED_SECRET]`.
- Run secret audit before opening a pull request.

## Redaction rules

- Deterministic local rules beat model-based detection.
- Avoid entropy-only detectors unless false positives are tightly bounded.
- Tests for new provider patterns must prove full redaction and comma-separated redaction.

## Emergency request tracing

`promptcloak serve --debug-requests` logs raw request bodies. Use only with local fixture values.
