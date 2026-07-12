# Monitor

Verify each published surface after deployment.

## GitHub

- `ci`, `codeql`, and `release` workflows passed for release commit/tag.
- Release includes wheel, source archive, Helm chart, and `SHA256SUMS`.
- Downloaded assets match `SHA256SUMS`; build provenance verifies.
- Dependabot, secret-scanning, and code-scanning alerts remain empty.

## Container and Helm

```bash
docker pull ghcr.io/bvolpato/promptcloak:0.1.7
docker run --rm --entrypoint promptcloak ghcr.io/bvolpato/promptcloak:0.1.7 version
helm lint ./charts/promptcloak
```

## Homebrew and site

- `brew info bvolpato/tap/promptcloak` reports release version.
- Formula install/test passes.
- `https://bvolpato.github.io/promptcloak/` matches `site/` and loads assets.

## Local service

```bash
systemctl --user is-enabled promptcloak.service
systemctl --user is-active promptcloak.service
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/openapi.json | jq -r .info.version
docker exec promptcloak-local promptcloak version
curl -fsS http://127.0.0.1:8787/healthz
```

Both health endpoints must report redaction enabled, `detect-secrets`, and `telemetry:false`.
Both runtimes must report release version. `promptcloak-local` must bind loopback, restart unless
stopped, and run with raw-request debug off.
