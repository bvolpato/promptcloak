# Security audit

Date: 2026-07-17

Scope: local proxy, redaction engine, library helpers, config loading, emergency tracing, audit logs, docs, CI, and public git history hygiene.

## Findings fixed

- Emergency tracing now masks every `X-Redact-*` header. These headers can contain exact-match rules, so logging them raw was unsafe.
- Emergency tracing masks credential-shaped headers, including `Proxy-Authorization` and custom secret headers.
- Target URLs with embedded userinfo are now rejected. This avoids accidental credential forwarding through `https://user:pass@host` URLs.
- Query parameters and unencoded non-JSON bodies are now redacted before forwarding. Multipart binary bytes are preserved.
- Docker Compose binds to loopback by default.
- Config and encryption-key writes are atomic and private from creation.
- Release builds use locked dependencies, isolated permissions, disabled caches, and non-persistent checkout credentials.
- Dependabot delays patch updates for 3 days, minor updates for 7 days, and major updates for 30 days. Security updates remain immediate.
- JSON, text, and streaming content-type checks are now case-insensitive.
- Malformed and unresolvable dynamic target URLs return client errors instead of server errors.
- Secret-shaped JSON keys and short values in explicit password or credential fields are redacted.
- Provider responses pass through without scanning or redaction by design.
- Custom regex rules reject invalid or empty-matching expressions, and custom names cannot select built-in replacement logic.
- Release publication verifies signed tags on `main`, rejects duplicate releases, and serializes same-tag runs.
- Helm pods do not mount Kubernetes API credentials.

## End-to-end coverage

- Nested Responses API payload redaction across messages, tools, metadata, comma-separated provider fixtures, and custom tail rules.
- Audit log events contain counts and rule names without fixture secret values.
- Anthropic/Claude-style `/v1/messages` forwarding uses upstream `x-api-key` without leaking local client auth.
- Text request body redaction works with case-insensitive content types.
- Provider response bodies and representation headers remain unchanged.
- Target URL userinfo is rejected.
- Emergency tracing masks redaction rule headers and keeps redacted body clean.
- Provider fixtures cover Cloudflare, signed URLs, encrypted PEM/PGP keys, and newer AI providers including Z.AI, MiniMax, DeepSeek, Codex/OpenAI, xAI/Grok, and Fireworks.
- Nested provider bases such as `/api/v1` do not duplicate incoming `/v1` route prefixes.
- Library scanning covers Pydantic message metadata as well as message content.

## Fixture hygiene

Tests use provider-shaped fixture tokens built from split string prefixes. No real keys are used, and no contiguous key-shaped fixtures are committed.

## Remaining risks

- Provider responses are outside PromptCloak's request-redaction boundary.
- Detection is deterministic and format-based, so unknown provider key formats may need new rules.
- DNS private-target validation is not connection-pinned. Allow only trusted upstream hostnames.
- Emergency tracing intentionally logs raw request bodies; use only with local fixture data.
- This audit covers repository code and tests. No external penetration test was performed.
