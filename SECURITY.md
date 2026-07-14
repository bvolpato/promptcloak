# Security policy

PromptCloak is built to keep secrets local before LLM requests leave a machine.

## Reporting

Do not include real secrets, tokens, logs with credentials, or private prompts in public issues.

Report vulnerabilities privately through GitHub Security Advisories for this repository. If advisories are unavailable, open a minimal issue asking for a private contact path without details.

## Guarantees

- No telemetry, analytics, or phone-home behavior.
- Redaction runs locally with deterministic `detect-secrets` plugins plus provider rules.
- Request scanning stays in memory and does not write prompt bodies to temporary files.
- Audit logs contain redaction counts and rule names without storing secret values.
- Client-supplied auth headers are dropped unless forwarding is explicitly configured.
- Private/loopback target URLs are blocked by default to reduce SSRF risk.

## Limitations

- PromptCloak protects request bodies before forwarding. It cannot protect credentials intentionally used as upstream authentication.
- Encoded request bodies must be decompressed before redaction.
- Private-target checks validate DNS before connection but do not pin that resolution. Allow only trusted upstream hostnames.
- Emergency request tracing can print raw request bodies locally.
- Streaming response redaction is intentionally not attempted.
- Detection quality depends on known provider formats, labeled values, connection-string shapes, and configured tail/regex rules.
- Entropy-only matching is disabled to avoid unpredictable false positives.

## Recommended defaults

- Bind to `127.0.0.1`.
- Keep `target.forward_client_authorization: false`.
- Keep `target.block_private_targets: true`.
- Set `target.allowed_base_urls` when shared by teams.
- Store only secret tails in custom rules.
- Use full redaction mode.
- Add custom regex or tail rules for private/internal token formats.
