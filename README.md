# PromptCloak

[![CI](https://github.com/bvolpato/promptcloak/actions/workflows/ci.yml/badge.svg)](https://github.com/bvolpato/promptcloak/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/bvolpato/promptcloak)](https://github.com/bvolpato/promptcloak/releases)
[![License: MIT](https://img.shields.io/github/license/bvolpato/promptcloak)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776ab)](pyproject.toml)
[![Docker](https://img.shields.io/badge/GHCR-promptcloak-54d6a0)](https://github.com/bvolpato/promptcloak/pkgs/container/promptcloak)

**Run LLM requests through a local secret scrubber before they leave your machine.**

PromptCloak is for developers using coding agents, SDKs, and OpenAI-compatible backends that should never receive local credentials embedded in prompts. It runs on your machine, scans request bodies before forwarding, and replaces API keys, passwords, tokens, private keys, signed URLs, and custom matches.

No telemetry. No phone-home. No full-secret storage required.

![PromptCloak site preview](site/hero.png)

Website: `https://bvolpato.github.io/promptcloak/`
Repository: `https://github.com/bvolpato/promptcloak`

## What you get

| Need | Use |
| --- | --- |
| Protect coding agents and IDEs | Run `promptcloak serve` and point OpenAI-compatible clients at `http://127.0.0.1:8000/v1`. |
| Protect SDK calls in your app | Import `redact_messages`, `redact_params`, or `redact_payload`. |
| Route to different providers | Use config defaults or `X-Target-Base-URL` per request. |
| Prove redaction works | Send fixture tokens to an echo target instead of asking a model to repeat secrets. |

## What gets redacted

Default rules cover provider keys, personal access tokens, passwords, JWTs, signed URLs, URL credentials, PEM/PGP private keys, and common secret fields such as `api_key`, `token`, `authorization`, `password`, `signed_url`, and `credentials`.

Coverage is deterministic: `bc-detect-secrets` plus PromptCloak provider rules and your exact-tail or regex rules. Entropy-only matching is disabled so redaction stays predictable.

## Security boundary

- Request bodies are scanned before they leave your machine.
- Audit logs store counts and rule names, never secret values.
- Upstream auth headers still have to reach the provider when used for authentication.
- Unknown private token formats need a custom exact-tail or regex rule.
- `--debug-requests` can print raw local request bodies; use it only with fixture data.

## 60-second demo

```bash
brew tap bvolpato/tap
brew install promptcloak
promptcloak init --target-base-url https://api.openai.com/v1
export OPENAI_API_KEY="<upstream-provider-key>"
promptcloak serve
```

Send traffic through PromptCloak:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-5.5",
    "messages": [
      {
        "role": "user",
        "content": "Here is my .env: OPENAI_API_KEY=<api-key-like-value>"
      }
    ]
  }'
```

Upstream sees:

```text
OPENAI_API_KEY=[REDACTED_SECRET]
```

Partial masking is available, but full masking is safer and default:

```yaml
redaction:
  redact_mode: "partial"
```

## Deterministic redaction smoke

Do not verify redaction by asking an LLM to repeat what it received. Models can refuse, infer, summarize, or misstate what happened. Use an echo target:

```bash
FAKE_GEMINI_KEY="AI""zaSyFixtureToken000000000000000000000"

curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Target-Base-URL: https://httpbin.org/anything" \
  -H "Content-Type: application/json" \
  --data "$(jq -nc --arg key "$FAKE_GEMINI_KEY" \
    '{messages:[{role:"user",content:("GEMINI_API_KEY=" + $key)}]}')" \
  | jq -r '.json.messages[0].content'
```

Expected output:

```text
GEMINI_API_KEY=[REDACTED_SECRET]
```

PromptCloak audit logs include counts and rule names, never secret values.

## Install with Homebrew

```bash
brew tap bvolpato/tap
brew install promptcloak
promptcloak version
promptcloak init --target-base-url https://api.openai.com/v1
```

Foreground mode keeps the upstream key in your shell:

```bash
export OPENAI_API_KEY="<openai-upstream-key>"
promptcloak serve
```

Service mode needs the upstream key in config or service-manager env:

```bash
brew services start bvolpato/tap/promptcloak
```

## Install release with uv

```bash
uv tool install \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.5/promptcloak-0.1.5-py3-none-any.whl
promptcloak doctor
```

## Install from source

```bash
git clone https://github.com/bvolpato/promptcloak.git
cd promptcloak
uv sync --extra dev
uv run promptcloak doctor
```

## Use as a library

PromptCloak can run without proxy service. Import redaction helpers and filter request values before passing them to any SDK. PromptCloak does not install OpenAI, LiteLLM, LangChain, or Anthropic SDKs; examples assume those are already in your app.

```bash
uv add \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.5/promptcloak-0.1.5-py3-none-any.whl
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
    RedactionConfig(
        rules=[RuleConfig(type="exact", value="abcd1234", name="tail-only")]
    )
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
    "model": "openai/gpt-5.5",
    "messages": [{"role": "user", "content": "secret=<api-key-like-value>"}],
}

response = httpx.post(
    "https://api.openai.com/v1/chat/completions",
    headers={"Authorization": "Bearer <provider-api-key>"},
    json=redact_payload(payload),
)
```

## Run

```bash
uv run promptcloak init --target-base-url https://api.openai.com/v1
export OPENAI_API_KEY="<openai-upstream-key>"
uv run promptcloak serve
```

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
  scan_responses: false
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

Best practice: store only key tails in `rules`, never full secrets.

## Supported routes

PromptCloak forwards any path, with first-class tests for:

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/completions`
- `/v1/models`
- `/v1/messages` for Claude-compatible gateways

It preserves streaming responses, tools, structured outputs, vision payloads, and unknown provider fields because it redacts recursively without reshaping request schemas.

## Dynamic backends

Set default backend in config, or override per request:

```bash
curl http://127.0.0.1:8000/v1/responses \
  -H "X-Target-Base-URL: https://api.openai.com/v1" \
  -H "X-Target-API-Key: $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.5","input":"scan this <api-key-like-value>"}'
```

Set `X-Target-API-Key-Header: x-api-key` for Anthropic-style upstream authentication.

Configured target keys are bound to `target.default_base_url`. A request that changes
`X-Target-Base-URL` must also provide its matching `X-Target-API-Key` or
`X-Target-Authorization`.

Use `target.allowed_base_urls` for strict allowlists.

Per-request rules are exact matches by default. Regex rules remain available in trusted config.
Set `redaction.allow_extra_regex_rules: true` only for authenticated clients you trust.

## Provider targets

PromptCloak forwards routes without reshaping provider payloads. Pick a default target
in config, or pass the target per request.

| Target | Base URL | Auth header | Notes |
| --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `authorization` | Native Chat Completions, Responses API, models, tools, streaming. |
| OpenRouter | `https://openrouter.ai/api/v1` | `authorization` | OpenAI-compatible gateway. Use provider-prefixed model names. |
| Anthropic / Claude-compatible | `https://api.anthropic.com` | `x-api-key` | Forward `/v1/messages`; PromptCloak does not translate OpenAI JSON into Anthropic JSON. |
| Local Ollama or vLLM | `http://127.0.0.1:11434/v1` or another local `/v1` endpoint | provider-specific | Set `block_private_targets: false` only for local-only configs. |

OpenAI default:

```bash
export OPENAI_API_KEY="<openai-upstream-key>"
promptcloak init --target-base-url https://api.openai.com/v1
promptcloak serve
```

OpenRouter per request:

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

## Codex

Codex speaks OpenAI Responses. Some gateways expose Chat Completions only. PromptCloak can bridge Codex `/v1/responses` traffic to upstream `/v1/chat/completions` with `compat.responses_to_chat: true`.

OpenRouter is one Codex-friendly target because PromptCloak can bridge Codex Responses traffic to Chat Completions. For OpenRouter through PromptCloak, put `env_key = "OPENROUTER_API_KEY"` in the Codex provider. Codex attaches the key to localhost requests, and PromptCloak forwards that Authorization header to the allowed OpenRouter upstream.

PromptCloak config:

```bash
mkdir -p ~/.config/promptcloak
cp examples/promptcloak-openrouter.config.yaml ~/.config/promptcloak/config.yaml
export OPENROUTER_API_KEY="<openrouter-upstream-key>"
uv run promptcloak serve
```

Relevant PromptCloak settings:

```yaml
target:
  default_base_url: https://openrouter.ai/api/v1
  api_key: null
  forward_client_authorization: true
  allowed_base_urls:
    - https://openrouter.ai/api/v1

compat:
  responses_to_chat: true
```

Codex profile:

`~/.codex/config.toml`

```toml
model = "openai/gpt-oss-120b"
model_provider = "promptcloak-openrouter"

[model_providers.promptcloak-openrouter]
name = "PromptCloak OpenRouter"
base_url = "http://127.0.0.1:8000/v1"
env_key = "OPENROUTER_API_KEY"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
```

Or keep it as a separate profile:

```bash
mkdir -p ~/.codex
cp examples/codex-openrouter-promptcloak.config.toml ~/.codex/openrouter-promptcloak.config.toml
codex -p openrouter-promptcloak
```

Smoke test:

```bash
codex -p openrouter-promptcloak --sandbox read-only --ask-for-approval never exec \
  --cd /home/bruno/githubworkspace/promptcloak \
  "Reply with exactly: promptcloak-openrouter-ok"
```

Confirm Chat Completions separately:

```bash
curl -fsS http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"Reply exactly: ok"}]}' \
  | jq -r '.choices[0].message.content'
```

Use any OpenRouter model by changing the profile `model`. Add `server.api_key` only if you bind PromptCloak beyond localhost.

Bridge notes:

- Do not put raw keys in TOML. Put the env var name in `env_key`.
- Keep `target.allowed_base_urls` tight when forwarding client auth.
- Text responses and standard function calls are translated.
- PromptCloak redacts before translation.
- Leave `compat.responses_to_chat` off for upstreams with native `/v1/responses`.

## OpenCode

OpenCode supports custom OpenAI-compatible providers through `@ai-sdk/openai-compatible` and `options.baseURL`.

Option A: set upstream provider on PromptCloak:

```bash
export PROMPTCLOAK_TARGET_BASE_URL="https://api.openai.com/v1"
export PROMPTCLOAK_TARGET_API_KEY="<openai-upstream-key>"
promptcloak serve
```

Option B: set upstream provider per request from OpenCode headers:

`opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "promptcloak": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "PromptCloak",
      "options": {
        "baseURL": "http://127.0.0.1:8000/v1",
        "headers": {
          "X-Target-Base-URL": "https://api.openai.com/v1",
          "X-Target-API-Key": "{env:OPENAI_API_KEY}"
        }
      },
      "models": {
        "gpt-5.5": {
          "name": "GPT-5.5 via PromptCloak"
        }
      }
    }
  },
  "model": "promptcloak/gpt-5.5"
}
```

Upstream provider URL and key are `X-Target-Base-URL` and `X-Target-API-Key`, or `PROMPTCLOAK_TARGET_BASE_URL` and `PROMPTCLOAK_TARGET_API_KEY` when configured on PromptCloak.

## Claude Code

Claude Code uses Anthropic-compatible traffic, not OpenAI Chat Completions. PromptCloak can still redact and forward Claude Code requests when upstream is Anthropic-compatible or an LLM gateway that accepts Claude Code traffic.

Config:

```yaml
target:
  default_base_url: https://api.anthropic.com
  api_key: ${ANTHROPIC_UPSTREAM_API_KEY}
  api_key_header: x-api-key
```

Shell:

```bash
export ANTHROPIC_UPSTREAM_API_KEY="<anthropic-upstream-key>"
export ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
export ANTHROPIC_API_KEY="${PROMPTCLOAK_LOCAL_API_KEY:-placeholder}"
export DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
promptcloak serve
claude
```

PromptCloak forwards `/v1/messages` to configured upstream. It does not translate OpenAI protocol into Anthropic protocol.

## Redaction Engine

PromptCloak uses `bc-detect-secrets` directly, plus deterministic rules for provider tokens and user-defined exact-tail or regex matches. No model runtime involved.

Coverage includes fixture-shaped examples for:

- GitHub classic and fine-grained PATs
- Atlassian API tokens
- OpenAI project/API keys
- Gemini API keys
- Anthropic API keys
- OpenRouter keys
- Z.AI, MiniMax, DeepSeek, Codex/OpenAI, xAI/Grok, and Fireworks keys when labeled or prefix-shaped
- GitLab, Slack, Stripe, AWS, Google API keys
- 1Password, Databricks, DigitalOcean, Hugging Face, Linear, npm, PyPI, SendGrid, Telegram, Twilio, Vault, Shopify, Sentry
- Cloudflare API keys/tokens in assignment form or `X-Auth-Key` / `CF-Access-Token` headers
- AWS, Google Cloud Storage, and Azure signed URL signatures and credential parameters
- JWTs
- PEM, encrypted PEM, and PGP private keys
- Authorization-style headers and URL credentials in request bodies
- `password=...`, `token=...`, `api_key=...`
- JSON object fields named like `api_key`, `token`, `secret`, `password`, `authorization`, `credentials`, `signed_url`, or `sas_token`
- User exact-tail and regex rules

Every scan is local. PromptCloak never calls an LLM to detect secrets. Entropy-only
matching is intentionally disabled; use custom rules for opaque internal formats.

## Encrypt rules at rest

```bash
uv run promptcloak encrypt-rules
```

This creates `~/.config/promptcloak/key` with mode `0600`, encrypts `redaction.rules` using AES-GCM, writes `redaction.encrypted_rules`, and clears plain rules.

You can also provide key material through:

```bash
export PROMPTCLOAK_CONFIG_KEY="base64-url-safe-32-byte-key"
```

## Docker

Published image:

```bash
export OPENAI_API_KEY="<openai-upstream-key>"

docker run -d --name promptcloak --rm \
  -p 127.0.0.1:8000:8000 \
  -e PROMPTCLOAK_TARGET_BASE_URL=https://api.openai.com/v1 \
  -e PROMPTCLOAK_TARGET_API_KEY="$OPENAI_API_KEY" \
  ghcr.io/bvolpato/promptcloak:0.1.5

curl -fsS http://127.0.0.1:8000/healthz
docker stop promptcloak
```

Local build:

```bash
docker build -t promptcloak:local .
docker run -d --name promptcloak --rm \
  -p 127.0.0.1:8000:8000 \
  -e PROMPTCLOAK_TARGET_BASE_URL=https://api.openai.com/v1 \
  -e PROMPTCLOAK_TARGET_API_KEY="$OPENAI_API_KEY" \
  promptcloak:local

curl -fsS http://127.0.0.1:8000/healthz
docker stop promptcloak
```

Compose:

```bash
export OPENAI_API_KEY="<openai-upstream-key>"
docker compose up --build
```

## Helm

Local chart:

```bash
helm install promptcloak ./charts/promptcloak \
  --set env.PROMPTCLOAK_TARGET_DEFAULT_BASE_URL=https://api.openai.com/v1 \
  --set secretEnv.PROMPTCLOAK_TARGET_API_KEY="$OPENAI_API_KEY"

kubectl wait deployment/promptcloak --for=condition=Available --timeout=90s
export PROMPTCLOAK_SERVER_API_KEY="$(
  kubectl get secret promptcloak-secret \
    -o jsonpath='{.data.PROMPTCLOAK_SERVER_API_KEY}' | base64 --decode
)"
kubectl port-forward svc/promptcloak 8000:8000
```

In another shell:

```bash
curl -fsS http://127.0.0.1:8000/healthz
helm uninstall promptcloak
```

Use locally built images in Kind:

```bash
docker build -t promptcloak:local .
kind load docker-image promptcloak:local
helm install promptcloak ./charts/promptcloak \
  --set image.repository=promptcloak \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.PROMPTCLOAK_TARGET_DEFAULT_BASE_URL=https://api.openai.com/v1 \
  --set secretEnv.PROMPTCLOAK_TARGET_API_KEY="$OPENAI_API_KEY"
```

Release asset:

```bash
helm pull https://github.com/bvolpato/promptcloak/releases/download/v0.1.5/promptcloak-0.1.5.tgz
helm install promptcloak ./promptcloak-0.1.5.tgz \
  --set env.PROMPTCLOAK_TARGET_DEFAULT_BASE_URL=https://api.openai.com/v1 \
  --set secretEnv.PROMPTCLOAK_TARGET_API_KEY="$OPENAI_API_KEY"
```

Helm enables proxy authentication and generates a key by default. Pass
`--set-string serverAuth.apiKey="$PROMPTCLOAK_SERVER_API_KEY"` to choose it. Send
`Authorization: Bearer $PROMPTCLOAK_SERVER_API_KEY` on proxied requests. Health probes remain
unauthenticated.

## Security model

PromptCloak protects request bodies before they leave your machine. It masks sensitive auth headers in debug logs, but it cannot remove upstream credentials from provider-bound auth headers because providers need those credentials to authenticate the request. Recommended setup:

- Put upstream provider key in PromptCloak config or env.
- Keep `forward_client_authorization: false` unless you intentionally want client auth forwarded.
- Use `api_key_header: x-api-key` for Anthropic-compatible upstreams.
- Set `server.api_key` only when exposing PromptCloak beyond `127.0.0.1`.
- Store only secret tails in redaction rules.
- Keep `block_private_targets: true`.
- Set `allowed_base_urls` in shared/team installs.
- Keep response scanning off unless you need it; streaming response redaction is intentionally not attempted yet.
- Add custom rules for internal tokens or providers without stable public prefixes.
- In library mode, call `redact_messages`, `redact_params`, or `redact_payload` before SDK calls.

## Emergency request tracing

`promptcloak serve --debug-requests` logs raw request bodies before redaction. Use it only with local fixture data when an echo target is not enough. Auth, target-key, and redaction-rule headers are masked; body text is not.

## Development

```bash
uv sync --extra dev
uv run scripts/audit_secrets.py
uv run pytest
uv run ruff check .
uv build
uv run promptcloak scan 'OPENAI_API_KEY=<api-key-like-value>'
```

Tests cover nested OpenAI, Responses, and Claude-style payloads, dynamic upstream
headers, audit logs, emergency tracing, response scanning, target allowlists, text
bodies, and provider-shaped fixture tokens. Fixtures are split in source so no real or
contiguous fake keys are committed.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [SECURITY_AUDIT.md](SECURITY_AUDIT.md) before opening issues or pull requests. Never post real secrets in public project surfaces.

## Distribution

PromptCloak ships GitHub releases with source, wheel, Helm chart, Homebrew formula, and GHCR image artifacts.
