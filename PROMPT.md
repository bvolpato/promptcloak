# Integrate PromptCloak

Integrate PromptCloak so secrets in LLM request content are redacted before they
leave this machine or application process. Complete setup, configuration, and
verification while following existing project conventions.

## Before editing

1. Inspect current LLM clients, agent configs, package manager, runtime, and deployment model.
2. Read current PromptCloak README and use its current release commands. PromptCloak is distributed through GitHub releases rather than PyPI.
3. Choose proxy mode or Python library mode based on where requests are created.
4. Keep changes limited to PromptCloak integration and required documentation.

Use proxy mode for coding agents, non-Python applications, shared local routing,
or clients that support a custom OpenAI or Anthropic base URL. Use library mode
when Python code constructs requests and can redact values immediately before an
SDK call.

## Install

Choose one proxy installation method.

Homebrew:

```bash
brew tap bvolpato/tap
brew install promptcloak
promptcloak version
```

uv tool:

```bash
uv tool install \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.8/promptcloak-0.1.8-py3-none-any.whl
promptcloak version
```

Docker:

```bash
docker pull ghcr.io/bvolpato/promptcloak:0.1.8
docker run --rm --entrypoint promptcloak \
  ghcr.io/bvolpato/promptcloak:0.1.8 version
```

Source checkout:

```bash
git clone https://github.com/bvolpato/promptcloak.git
cd promptcloak
uv sync --extra dev --locked
uv run promptcloak version
```

For Python library mode, add release wheel to existing uv project:

```bash
uv add \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.8/promptcloak-0.1.8-py3-none-any.whl
```

## Security rules

- Leave real credentials in existing environment variables or secret managers. Never print, paste, move, or commit them.
- Use fixture-only values containing `FixtureToken` for tests and examples.
- Bind proxy to `127.0.0.1` unless remote access is explicitly required.
- Require `server.api_key` before binding beyond loopback.
- Keep `block_private_targets: true` unless a trusted local upstream is required.
- Leave `debug_requests: false` and do not add telemetry.
- Use full redaction. Add custom tail-only rules for unknown internal formats.
- Detection must remain deterministic; do not add entropy-only matching.
- Provider authentication belongs outside request content. PromptCloak forwards
  configured upstream credentials and masks sensitive headers in debug output.

## Proxy mode

Create config without placing literal keys in it:

```yaml
server:
  host: 127.0.0.1
  port: 8000
  api_key: null
  debug_requests: false

target:
  default_base_url: https://api.example.com/v1
  api_key: ${UPSTREAM_API_KEY}
  api_key_header: authorization
  forward_client_authorization: false
  allowed_base_urls: []
  block_private_targets: true

redaction:
  enabled: true
  engine: detect-secrets
  redact_mode: full
```

Use `api_key_header: x-api-key` for Anthropic-compatible upstreams. Keep one
configured target when possible. For per-request routing, allow each public base
URL explicitly and send matching `X-Target-Base-URL` and `X-Target-API-Key`
headers. Never forward a configured target key to a different host.

Point OpenAI-compatible clients at `http://127.0.0.1:8000/v1`. Point Claude Code
at `http://127.0.0.1:8000` through `ANTHROPIC_BASE_URL`. Some SDKs require a local
API-key value even when PromptCloak has no `server.api_key`; use a non-secret
placeholder in that case. Do not invent a PromptCloak key unless local proxy auth
is enabled.

For Codex, OpenCode, and Claude Code, follow their dedicated README sections.
Preserve protocol expectations: Codex uses Responses, OpenCode can use an
OpenAI-compatible provider, and Claude Code uses Anthropic Messages.

## Python library mode

Install current PromptCloak release from README, then redact immediately before
each SDK call:

```python
from promptcloak import redact_messages, redact_params, redact_payload

safe_messages = redact_messages(messages)
safe_params = redact_params(model=model, messages=messages, tools=tools)
safe_payload = redact_payload(payload)
```

Pick the helper that matches the call shape:

- `redact_messages` for message arrays, including LangChain message objects.
- `redact_params` for OpenAI, LiteLLM, and similar keyword arguments.
- `redact_payload` for raw JSON-compatible request bodies.

Do not mutate caller-owned data or redact provider authentication passed outside
request content. Cover every LLM call path, including retries, streaming calls,
tool payloads, and background jobs.

## Verification

1. Run project lint, type checks, and focused tests.
2. In proxy mode, confirm `GET /healthz` reports redaction enabled and telemetry disabled.
3. Test redaction against an echo target, never a model:

```bash
FAKE_KEY="AI""zaSyFixtureToken000000000000000000000"

curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Target-Base-URL: https://httpbin.org/anything" \
  -H "Content-Type: application/json" \
  --data "$(jq -nc --arg key "$FAKE_KEY" \
    '{messages:[{role:"user",content:("GEMINI_API_KEY=" + $key)}]}')" \
  | jq -r '.json.messages[0].content'
```

Expected output:

```text
GEMINI_API_KEY=[REDACTED_SECRET]
```

Confirm fixture value is absent from logs. Report selected mode, changed files,
credential handling, commands run, and exact verification result.
