# PromptCloak

[![CI](https://github.com/bvolpato/promptcloak/actions/workflows/ci.yml/badge.svg)](https://github.com/bvolpato/promptcloak/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bvolpato/promptcloak/actions/workflows/codeql.yml/badge.svg)](https://github.com/bvolpato/promptcloak/actions/workflows/codeql.yml)
[![Release](https://img.shields.io/github/v/release/bvolpato/promptcloak)](https://github.com/bvolpato/promptcloak/releases)
[![License: MIT](https://img.shields.io/github/license/bvolpato/promptcloak)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776ab)](pyproject.toml)
[![Docker](https://img.shields.io/badge/GHCR-promptcloak-54d6a0)](https://github.com/bvolpato/promptcloak/pkgs/container/promptcloak)

**Redact secrets before prompts reach an LLM provider.**

PromptCloak is a local proxy and Python library for coding agents, SDKs, and
OpenAI-compatible backends. It scans request bodies and query parameters, replaces
detected credentials and custom matches, then forwards the request.

Scanning stays local. PromptCloak has no telemetry or phone-home behavior.

![PromptCloak site preview](site/hero.png)

Website: `https://bvolpato.github.io/promptcloak/`

Agent integration prompt: [`PROMPT.md`](PROMPT.md)

## Choose a mode

| Need | Use |
| --- | --- |
| Protect coding agents and IDEs | Run `promptcloak serve` and point OpenAI-compatible clients at `http://127.0.0.1:8000/v1`. |
| Protect SDK calls in your app | Import `redact_messages`, `redact_params`, or `redact_payload`. |

## Coverage

Default rules cover provider keys, personal access tokens, passwords, JWTs,
signed URLs, URL credentials, PEM/PGP private keys, and common secret fields such
as `api_key`, `token`, `authorization`, `password`, `signed_url`, and
`credentials`.

Detection uses deterministic provider rules plus your exact-tail or regex rules.
Entropy-only matching is disabled to avoid unpredictable false positives.

## Security boundary

- Request bodies and query parameters are scanned before they leave your machine.
- Audit logs record redaction counts and rule names without storing secret values.
- PromptCloak strips cookies and secret-named client headers. Provider credentials are
  added from config or dedicated `X-Target-*` headers after that filtering step.
- Unknown private token formats need a custom exact-tail or regex rule.

See [SECURITY.md](SECURITY.md) for deployment defaults and remaining limits.

## Install

Homebrew:

```bash
brew tap bvolpato/tap
brew install promptcloak
promptcloak version
```

uv:

```bash
uv tool install \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.9/promptcloak-0.1.9-py3-none-any.whl
promptcloak doctor
```

Source:

```bash
git clone https://github.com/bvolpato/promptcloak.git
cd promptcloak
uv sync --extra dev --locked
uv run promptcloak doctor
```

ASGI servers can load `promptcloak.asgi:app` directly. Importing CLI or proxy
helpers does not load user config until a command or app requests it.

## Run proxy

Configure an upstream, keep its key in your shell, and start PromptCloak:

```bash
promptcloak init --target-base-url https://api.openai.com/v1
export OPENAI_API_KEY="<openai-upstream-key>"
promptcloak serve
```

Point clients at `http://127.0.0.1:8000/v1`. For example:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.5",
    "messages": [{
      "role": "user",
      "content": "Here is my .env: OPENAI_API_KEY=<api-key-like-value>"
    }]
  }'
```

Provider receives `OPENAI_API_KEY=[REDACTED_SECRET]` in request content.

## Verify redaction

A model reply cannot verify the forwarded request. Send a fixture token to an echo
endpoint and inspect the echoed body:

```bash
FAKE_GEMINI_KEY="AI""zaSyFixtureToken000000000000000000000"

curl --compressed -fsS http://127.0.0.1:8000/post \
  -H "X-Target-Base-URL: https://postman-echo.com" \
  -H "Content-Type: application/json" \
  --data "$(jq -nc --arg key "$FAKE_GEMINI_KEY" \
    '{messages:[{role:"user",content:("GEMINI_API_KEY=" + $key)}]}')" \
  | jq -r '.data.messages[0].content'
```

Expected output:

```text
GEMINI_API_KEY=[REDACTED_SECRET]
```

Audit logs omit matched values and include counts and rule names. Homebrew users
can run PromptCloak as a background service after configuring its environment:

```bash
brew services start bvolpato/tap/promptcloak
```

## Use as a library

PromptCloak can run without running the proxy service. Import redaction helpers and filter
request values before passing them to any SDK. PromptCloak does not install OpenAI,
LiteLLM, LangChain, or Anthropic SDKs; examples assume those are already in your
app.

```bash
uv add \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.9/promptcloak-0.1.9-py3-none-any.whl
```

```python
from promptcloak import redact_messages, scan_messages

messages = [
    {
        "role": "user",
        "content": "Debug this .env: OPENAI_API_KEY=<api-key-like-value>",
    }
]

safe_messages = redact_messages(messages)
result = scan_messages(messages)

assert result.stats.redactions >= 1
```

For custom tail-only rules:

```python
from promptcloak import PromptCloak
from promptcloak.config import RedactionConfig, RuleConfig

cloak = PromptCloak(
    RedactionConfig(rules=[RuleConfig(type="exact", value="abcd1234", name="tail-only")])
)

safe_messages = cloak.messages(messages)
```

### OpenAI Python

```python
from openai import OpenAI
from promptcloak import redact_messages, redact_params

client = OpenAI()

messages = [{"role": "user", "content": "API key: <api-key-like-value>"}]

response = client.chat.completions.create(
    model="gpt-5.5",
    messages=redact_messages(messages),
)

response_api = client.responses.create(
    **redact_params(
        model="gpt-5.5",
        input="Summarize this config: OPENAI_API_KEY=<api-key-like-value>",
    )
)
```

### LiteLLM

```python
from litellm import completion
from promptcloak import redact_params

messages = [{"role": "user", "content": "GEMINI_API_KEY=<api-key-like-value>"}]

response = completion(
    **redact_params(
        model="openai/gpt-5.5",
        messages=messages,
    )
)
```

### LangChain

Tuple-style messages:

```python
from langchain_openai import ChatOpenAI
from promptcloak import redact_messages

llm = ChatOpenAI(model="gpt-5.5")

response = llm.invoke(
    redact_messages(
        [
            ("system", "You are concise."),
            ("human", "Here is my token: <api-key-like-value>"),
        ]
    )
)
```

LangChain message objects:

```python
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from promptcloak import redact_messages

llm = ChatOpenAI(model="gpt-5.5")

response = llm.invoke(
    redact_messages(
        [
            HumanMessage(content="Here is my token: <api-key-like-value>"),
        ]
    )
)
```

### Anthropic Python

```python
from anthropic import Anthropic
from promptcloak import redact_messages

client = Anthropic()

response = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=1024,
    messages=redact_messages(
        [{"role": "user", "content": "ANTHROPIC_API_KEY=<api-key-like-value>"}]
    ),
)
```

### LlamaIndex

```python
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI
from promptcloak import redact_messages

llm = OpenAI(model="gpt-5.5")

response = llm.chat(
    redact_messages(
        [
            ChatMessage(role="user", content="Here is my token: <api-key-like-value>"),
        ]
    )
)
```

### Raw HTTP or custom clients

```python
import httpx
from promptcloak import redact_payload

payload = {
    "model": "gpt-5.5",
    "messages": [{"role": "user", "content": "secret=<api-key-like-value>"}],
}

response = httpx.post(
    "https://api.openai.com/v1/chat/completions",
    headers={"Authorization": "Bearer <provider-api-key>"},
    json=redact_payload(payload),
)
```

## Configuration

Default config: `~/.config/promptcloak/config.yaml`

```yaml
server:
  host: 127.0.0.1
  port: 8000
  api_key: null
  max_request_body_bytes: 33554432

target:
  default_base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
  api_key_header: authorization
  forward_client_authorization: false
  timeout_seconds: 180
  allowed_base_urls: []
  block_private_targets: true

redaction:
  enabled: true
  engine: detect-secrets
  redact_mode: full
  encrypted: false
  max_extra_rules: 20
  max_extra_rule_chars: 1024
  allow_extra_regex_rules: false
  rules:
    - type: exact
      value: abcd1234
      name: tail-only-example
    - type: regex
      value: sk-[A-Za-z0-9_-]{20,}
      name: openai-style-token
```

Store only key tails in exact rules. Full masking is default; partial masking is
available through `redact_mode: partial`.

## Supported routes

PromptCloak forwards any path, with first-class tests for:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/completions`
- `/v1/models`
- `/v1/messages` for Claude-compatible gateways

Tests cover streaming responses, tool payloads, and vision payloads. PromptCloak
redacts recursively without reshaping JSON request schemas.

## Provider targets

Set default backend in config, or choose one per request:

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "X-Target-Base-URL: https://api.openai.com/v1" \
  -H "X-Target-API-Key: $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.5","input":"scan this <api-key-like-value>"}'
```

Set `X-Target-API-Key-Header: x-api-key` for Anthropic-style upstream authentication.

Configured target keys are bound to `target.default_base_url`. A dynamic target that
requires authentication must receive its key through `X-Target-API-Key` or
`X-Target-Authorization`; PromptCloak never reuses configured key for another host.

An empty `target.allowed_base_urls` permits any public target. Add URLs to restrict
dynamic routing. Set `block_private_targets: false` only for trusted local targets.

Per-request rules are exact matches by default. Regex rules remain available in trusted config.
Set `redaction.allow_extra_regex_rules: true` only for authenticated clients you trust.

PromptCloak forwards routes without reshaping provider payloads.

| Target | Base URL | Auth header | Notes |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `authorization` | Native Chat Completions, Responses API, models, tools, streaming. |
| OpenRouter | `https://openrouter.ai/api/v1` | `authorization` | Native Chat Completions and Responses. Use provider-prefixed model names. |
| Anthropic / Claude-compatible | `https://api.anthropic.com` | `x-api-key` | Forward `/v1/messages`; PromptCloak does not translate OpenAI JSON into Anthropic JSON. |
| Local Ollama or vLLM | `http://127.0.0.1:11434/v1` or another local `/v1` endpoint | provider-specific | Set `block_private_targets: false` only for local-only configs. |

OpenRouter per request:

```yaml
target:
  allowed_base_urls:
    - https://openrouter.ai/api/v1
```

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Target-Base-URL: https://openrouter.ai/api/v1" \
  -H "X-Target-API-Key: $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"scan this <api-key-like-value>"}]}'
```

Anthropic-compatible target:

```bash
curl http://127.0.0.1:8000/v1/messages \
  -H "X-Target-Base-URL: https://api.anthropic.com" \
  -H "X-Target-API-Key: $ANTHROPIC_API_KEY" \
  -H "X-Target-API-Key-Header: x-api-key" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-8","max_tokens":256,"messages":[{"role":"user","content":"scan this <api-key-like-value>"}]}'
```

Local OpenAI-compatible target:

```yaml
target:
  default_base_url: http://127.0.0.1:11434/v1
  api_key: null
  allowed_base_urls:
    - http://127.0.0.1:11434/v1
  block_private_targets: false
```

## Codex with OpenRouter

OpenRouter accepts native Responses requests, so no compatibility bridge is needed.
Keep OpenRouter key in environment and send it through PromptCloak's dedicated target
header. Generic client `Authorization` is not forwarded.

Start PromptCloak:

```bash
mkdir -p ~/.config/promptcloak
cp examples/promptcloak-openrouter.config.yaml ~/.config/promptcloak/config.yaml
export OPENROUTER_API_KEY="<openrouter-upstream-key>"
promptcloak serve
```

The checked-in PromptCloak config restricts dynamic routing to OpenRouter and leaves
`forward_client_authorization` and `responses_to_chat` disabled.

Install Codex profile:

```bash
mkdir -p ~/.codex
cp examples/codex-openrouter-promptcloak.config.toml \
  ~/.codex/openrouter-promptcloak.config.toml
```

Profile contents:

```toml
model = "openai/gpt-oss-120b"
model_provider = "promptcloak-openrouter"

[model_providers.promptcloak-openrouter]
name = "PromptCloak OpenRouter"
base_url = "http://127.0.0.1:8000/v1"
wire_api = "responses"
env_http_headers = { "X-Target-API-Key" = "OPENROUTER_API_KEY" }
http_headers = { "X-Target-Base-URL" = "https://openrouter.ai/api/v1" }
request_max_retries = 0
stream_max_retries = 0
```

Run interactive Codex:

```bash
codex -p openrouter-promptcloak
```

Non-interactive smoke test:

```bash
codex exec -p openrouter-promptcloak --strict-config \
  --sandbox read-only --ephemeral --cd "$PWD" \
  "Reply with exactly: promptcloak-openrouter-ok"
```

Use any OpenRouter Responses-capable model by changing profile `model`. For an older
gateway that only supports Chat Completions, enable `compat.responses_to_chat`; text
and standard function calls are translated after redaction.

## OpenCode

Current stable OpenCode config supports custom Chat Completions providers through
`@ai-sdk/openai-compatible`. Copy checked-in example into project, or merge provider
block into existing `opencode.json`:

```bash
cp examples/opencode-openrouter-promptcloak.json opencode.json
export OPENROUTER_API_KEY="<openrouter-upstream-key>"
```

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "promptcloak-openrouter": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "PromptCloak OpenRouter",
      "options": {
        "baseURL": "http://127.0.0.1:8000/v1",
        "headers": {
          "X-Target-Base-URL": "https://openrouter.ai/api/v1",
          "X-Target-API-Key": "{env:OPENROUTER_API_KEY}"
        }
      },
      "models": {
        "openai/gpt-oss-120b": {
          "name": "gpt-oss via PromptCloak"
        }
      }
    }
  },
  "model": "promptcloak-openrouter/openai/gpt-oss-120b"
}
```

Run:

```bash
opencode run -m promptcloak-openrouter/openai/gpt-oss-120b \
  --format json --dir "$PWD" \
  "Reply with exactly: promptcloak-opencode-ok"
```

For another Chat Completions target, replace base URL, environment variable, and
model ID. Use `PROMPTCLOAK_TARGET_BASE_URL` and `PROMPTCLOAK_TARGET_API_KEY` instead
when PromptCloak owns one fixed upstream.

## Claude Code

Claude Code sends Anthropic Messages requests. Configure provider key on PromptCloak,
then use separate local bearer token for proxy authentication:

```bash
export ANTHROPIC_UPSTREAM_API_KEY="<anthropic-upstream-key>"
export PROMPTCLOAK_TARGET_BASE_URL="https://api.anthropic.com"
export PROMPTCLOAK_TARGET_API_KEY="$ANTHROPIC_UPSTREAM_API_KEY"
export PROMPTCLOAK_TARGET_API_KEY_HEADER="x-api-key"
export PROMPTCLOAK_SERVER_API_KEY="<local-proxy-key>"

promptcloak serve

export ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
export ANTHROPIC_AUTH_TOKEN="$PROMPTCLOAK_SERVER_API_KEY"
export DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
claude
```

PromptCloak validates local bearer token, removes it, then adds upstream `x-api-key`.
It forwards `/v1/messages` without translating between OpenAI and Anthropic schemas.

## Redaction engine

PromptCloak uses `bc-detect-secrets`, provider token patterns, and user-defined
exact-tail or regex matches. It does not load or call a model.

Coverage includes fixture-shaped examples for:

- AI provider keys: OpenAI/Codex, Anthropic, Gemini, OpenRouter, Z.AI,
  MiniMax, DeepSeek, xAI/Grok, and Fireworks.
- Developer and cloud credentials: GitHub, GitLab, Atlassian, AWS,
  Cloudflare, Slack, Stripe, Google Cloud, Azure, npm, PyPI, and other common
  service tokens.
- Structured credentials: JWTs, signed URLs, URL userinfo, PEM keys, encrypted
  PEM keys, and PGP private keys.
- Labeled values and JSON fields such as `password`, `token`, `api_key`,
  `authorization`, `credentials`, `signed_url`, and `sas_token`.
- User-defined exact-tail and regex rules for private formats.

JSON is scanned structurally. Query parameters and unencoded non-JSON bodies, including
multipart requests, are scanned without changing unrelated bytes. Encoded request bodies are
rejected while redaction is enabled; decompress them before sending.

Every scan runs locally without an LLM. Entropy-only matching is disabled; use
custom rules for opaque internal formats.

## Encrypt rules at rest

```bash
uv run promptcloak encrypt-rules
```

This creates `~/.config/promptcloak/key` with mode `0600`, encrypts
`redaction.rules` with AES-GCM, writes `redaction.encrypted_rules`, and clears
plain rules.

You can also provide key material through:

```bash
export PROMPTCLOAK_CONFIG_KEY="base64-url-safe-32-byte-key"
```

## Docker

Published image:

```bash
# ~/.config/promptcloak/provider.env, mode 0600
PROMPTCLOAK_TARGET_BASE_URL=https://api.openai.com/v1
PROMPTCLOAK_TARGET_API_KEY=<openai-upstream-key>
```

```bash
docker run -d --name promptcloak --rm \
  -p 127.0.0.1:8000:8000 \
  --env-file "$HOME/.config/promptcloak/provider.env" \
  ghcr.io/bvolpato/promptcloak:0.1.9

curl --retry 10 --retry-connrefused --retry-delay 1 \
  -fsS http://127.0.0.1:8000/healthz
docker stop promptcloak
```

Build current checkout:

```bash
docker build -t promptcloak:local .
```

Compose:

```bash
export OPENAI_API_KEY="<openai-upstream-key>"
docker compose up --build
```

## Helm

Local chart:

```bash
kubectl create secret generic promptcloak-env \
  --from-env-file="$HOME/.config/promptcloak/kubernetes.env"

helm install promptcloak ./charts/promptcloak \
  --set env.PROMPTCLOAK_TARGET_DEFAULT_BASE_URL=https://api.openai.com/v1 \
  --set existingSecret=promptcloak-env

kubectl wait deployment/promptcloak --for=condition=Available --timeout=90s
export PROMPTCLOAK_SERVER_API_KEY="$(
  kubectl get secret promptcloak-env \
    -o jsonpath='{.data.PROMPTCLOAK_SERVER_API_KEY}' | base64 --decode
)"
kubectl port-forward svc/promptcloak 8000:8000
```

In another shell:

```bash
curl -fsS http://127.0.0.1:8000/healthz
helm uninstall promptcloak
```

Release asset:

```bash
helm pull https://github.com/bvolpato/promptcloak/releases/download/v0.1.9/promptcloak-0.1.9.tgz
helm install promptcloak ./promptcloak-0.1.9.tgz \
  --set env.PROMPTCLOAK_TARGET_DEFAULT_BASE_URL=https://api.openai.com/v1 \
  --set existingSecret=promptcloak-env
```

`kubernetes.env` must contain `PROMPTCLOAK_TARGET_API_KEY` and
`PROMPTCLOAK_SERVER_API_KEY`; keep file outside repository with mode `0600`.
Without `existingSecret`, chart generates proxy key and stores `secretEnv` values in
chart-managed Secret. Send `Authorization: Bearer $PROMPTCLOAK_SERVER_API_KEY` on
proxied requests. Health probes remain unauthenticated.

## Emergency request tracing

`promptcloak serve --debug-requests` logs raw request bodies before redaction. Restrict it to local fixture data and cases where an echo target is insufficient. Auth, target-key, and redaction-rule headers are masked; body text is visible.

## Development

```bash
uv sync --extra dev
uv run scripts/audit_secrets.py
uv run pytest
uv run ruff check .
uv build
uv run promptcloak scan 'OPENAI_API_KEY=<api-key-like-value>'
```

Fixtures are split in source so no real or contiguous fake keys are committed.
Release and test commands live in [CONTRIBUTING.md](CONTRIBUTING.md). Report
security problems through the private path in [SECURITY.md](SECURITY.md), without
posting real secrets.
