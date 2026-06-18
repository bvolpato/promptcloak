# PromptCloak

**Local OpenAI-compatible proxy and Python library that redacts secrets before prompts leave your machine.**

PromptCloak can sit between coding agents, SDKs, or apps and any OpenAI-compatible backend. It can also run in-process as a small Python filter. It scans values locally, redacts API keys, passwords, tokens, private keys, JWTs, and custom rules, then forwards or returns cleaned payloads.

No telemetry. No phone-home. No full-secret storage required.

![PromptCloak site preview](site/hero.png)

Website: `https://bvolpato.github.io/promptcloak/`
Repository: `https://github.com/bvolpato/promptcloak`

## 60-second demo

```bash
uv tool install \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.3/promptcloak-0.1.3-py3-none-any.whl
promptcloak init
export OPENROUTER_API_KEY="<upstream-provider-key>"
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

## Install from source

```bash
git clone https://github.com/bvolpato/promptcloak.git
cd promptcloak
uv sync --extra dev
uv run promptcloak doctor
```

## Install release

```bash
uv tool install \
  https://github.com/bvolpato/promptcloak/releases/download/v0.1.3/promptcloak-0.1.3-py3-none-any.whl
promptcloak doctor
```

## Use as a library

PromptCloak can run without proxy service. Import redaction helpers and filter request values before passing them to any SDK. PromptCloak does not install OpenAI, LiteLLM, LangChain, or Anthropic SDKs; examples assume those are already in your app.

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
        model="openrouter/openai/gpt-5.5",
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
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": "Bearer <provider-api-key>"},
    json=redact_payload(payload),
)
```

## Run

```bash
uv run promptcloak init --target-base-url https://openrouter.ai/api/v1
export OPENROUTER_API_KEY="<openrouter-upstream-key>"
uv run promptcloak serve
```

Default config: `~/.config/promptcloak/config.yaml`

```yaml
server:
  host: 127.0.0.1
  port: 8000
  api_key: null

target:
  default_base_url: https://openrouter.ai/api/v1
  api_key: ${OPENROUTER_API_KEY}
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

Use `target.allowed_base_urls` for strict allowlists.

## Codex

Codex speaks OpenAI Responses. Some gateways expose Chat Completions only. PromptCloak can bridge Codex `/v1/responses` traffic to upstream `/v1/chat/completions` with `compat.responses_to_chat: true`.

For OpenRouter through PromptCloak, put `env_key = "OPENROUTER_API_KEY"` in the Codex provider. Codex attaches the key to localhost requests, and PromptCloak forwards that Authorization header to the allowed OpenRouter upstream.

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
export PROMPTCLOAK_TARGET_BASE_URL="https://openrouter.ai/api/v1"
export PROMPTCLOAK_TARGET_API_KEY="<openrouter-upstream-key>"
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
          "X-Target-Base-URL": "https://openrouter.ai/api/v1",
          "X-Target-API-Key": "{env:OPENROUTER_API_KEY}"
        }
      },
      "models": {
        "openai/gpt-5.5": {
          "name": "GPT-5.5 via PromptCloak"
        }
      }
    }
  },
  "model": "promptcloak/openai/gpt-5.5"
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

PromptCloak uses `bc-detect-secrets` directly, plus local deterministic rules for provider tokens and user-defined exact-tail or regex matches. It does not depend on any model runtime.

Tests cover fake tokens shaped like:

- GitHub classic and fine-grained PATs
- Atlassian API tokens
- OpenAI project/API keys
- Gemini API keys
- Anthropic API keys
- OpenRouter keys
- GitLab, Slack, Stripe, AWS, Google API keys
- 1Password, Databricks, DigitalOcean, Hugging Face, Linear, npm, PyPI, SendGrid, Telegram, Twilio, Vault, Shopify, Sentry
- JWTs
- PEM private keys
- Authorization-style headers and URL credentials in request bodies
- `password=...`, `token=...`, `api_key=...`
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

```bash
docker build -t promptcloak .
docker run --rm -p 8000:8000 \
  -e PROMPTCLOAK_TARGET_BASE_URL=https://openrouter.ai/api/v1 \
  -e PROMPTCLOAK_TARGET_API_KEY="$OPENROUTER_API_KEY" \
  promptcloak:local
```

## Helm

```bash
helm install promptcloak ./charts/promptcloak \
  --set env.PROMPTCLOAK_TARGET_BASE_URL=https://openrouter.ai/api/v1 \
  --set secretEnv.PROMPTCLOAK_TARGET_API_KEY="$OPENROUTER_API_KEY"
```

## Security model

PromptCloak protects request bodies before they leave your machine. It cannot protect secrets already sent in upstream auth headers because providers need credentials. Recommended setup:

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

Test coverage includes unit and e2e fixtures for nested OpenAI/Responses/Claude-style
payloads, dynamic upstream headers, audit logs, emergency tracing, response scanning,
target allowlists, text bodies, and provider-shaped fake tokens. Fixtures are split in
source so no real or contiguous fake keys are committed.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [SECURITY_AUDIT.md](SECURITY_AUDIT.md) before opening issues or pull requests. Never post real secrets in public project surfaces.

## Status

PromptCloak ships GitHub releases with source and wheel artifacts. Homebrew, official container images, and PyPI can be added after the first public usage cycle.
