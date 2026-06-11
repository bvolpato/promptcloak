# Security Audit

Date: 2026-06-07

Scope: local proxy, redaction engine, library helpers, config loading, emergency tracing, audit logs, docs, CI, and public git history hygiene.

## Findings Fixed

- Emergency tracing now masks every `X-Redact-*` header. These headers can contain exact-match rules, so logging them raw was unsafe.
- Target URLs with embedded userinfo are now rejected. This avoids accidental credential forwarding through `https://user:pass@host` URLs.
- JSON, text, and streaming content-type checks are now case-insensitive.

## E2E Coverage

- Nested Responses API payload redaction across messages, tools, metadata, comma-separated provider fixtures, and custom tail rules.
- Audit log events contain counts and rule names without fixture secret values.
- Anthropic/Claude-style `/v1/messages` forwarding uses upstream `x-api-key` without leaking local client auth.
- Text request body redaction works with case-insensitive content types.
- Response scanning redacts JSON responses with case-insensitive content types.
- Target URL userinfo is rejected.
- Emergency tracing masks redaction rule headers and keeps redacted body clean.

## Fixture Hygiene

Tests use provider-shaped fixture tokens built from split string prefixes. No real keys are used, and no contiguous key-shaped fixtures are committed.

## Remaining Risks

- Streaming response redaction is not implemented.
- Detection is deterministic and format-based, so unknown provider key formats may need new rules.
- Emergency tracing intentionally logs raw request bodies; use only with local fixture data.
- This is an internal code audit, not an external penetration test.
