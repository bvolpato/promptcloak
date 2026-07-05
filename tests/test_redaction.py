from promptcloak.config import RedactionConfig, RuleConfig
from promptcloak.redaction import SecretRedactor
from tests.fixtures import EXPANDED_PROVIDER_FIXTURES, OPENAI_FAKE, PROVIDER_FIXTURES


def test_redacts_nested_openai_key() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    payload = {
        "messages": [
            {
                "role": "user",
                "content": f"debug this OPENAI_API_KEY={OPENAI_FAKE}",
            }
        ]
    }

    result = redactor.redact_payload(payload)

    content = result.value["messages"][0]["content"]
    assert OPENAI_FAKE not in content
    assert result.stats.redactions >= 1


def test_provider_api_keys_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="detect-secrets"))
    text = "\n".join(f"{name}={value}" for name, value in PROVIDER_FIXTURES.items())

    result = redactor.redact_text(text)

    for value in PROVIDER_FIXTURES.values():
        assert value not in result.value
    assert result.stats.redactions >= len(PROVIDER_FIXTURES)


def test_expanded_provider_tokens_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    text = "\n".join(f"{name}={value}" for name, value in EXPANDED_PROVIDER_FIXTURES.items())

    result = redactor.redact_text(text)

    for value in EXPANDED_PROVIDER_FIXTURES.values():
        assert value not in result.value
    assert result.stats.redactions >= len(EXPANDED_PROVIDER_FIXTURES)


def test_requested_ai_provider_credentials_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    payload = {
        "OPENAI_API_KEY": PROVIDER_FIXTURES["openai_key"],
        "GEMINI_API_KEY": PROVIDER_FIXTURES["gemini_api_key"],
        "ANTHROPIC_API_KEY": PROVIDER_FIXTURES["anthropic_api_key"],
        "DEEPSEEK_API_KEY": PROVIDER_FIXTURES["deepseek_api_key"],
        "MINIMAX_API_KEY": PROVIDER_FIXTURES["minimax_api_key"],
        "FIREWORKS_API_KEY": PROVIDER_FIXTURES["fireworks_api_key"],
        "XAI_API_KEY": PROVIDER_FIXTURES["xai_api_key"],
        "ZAI_API_KEY": "zai-provider-token-without-stable-prefix",
        "CODEX_API_KEY": "codex-provider-token-without-stable-prefix",
        "CODEX_ACCESS_TOKEN": "codex-access-token-without-stable-prefix",
    }

    result = redactor.redact_payload(payload)

    for value in payload.values():
        assert value not in result.value.values()
    assert set(result.value.values()) == {"[REDACTED_SECRET]"}
    assert result.stats.rule_hits["sensitive_field"] == len(payload)


def test_cloudflare_headers_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    cloudflare_key = EXPANDED_PROVIDER_FIXTURES["cloudflare_api_key"]
    text = "\n".join(
        [
            f"X-Auth-Key: {cloudflare_key}",
            f"CF-Access-Token: {cloudflare_key}",
            f"CLOUDFLARE_API_TOKEN={cloudflare_key}",
        ]
    )

    result = redactor.redact_text(text)

    assert cloudflare_key not in result.value
    assert result.value.count("[REDACTED_SECRET]") == 3


def test_signed_url_query_parameters_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    aws_signature = "a" * 64
    google_signature = "b" * 64
    azure_signature = "c" * 64
    text = "\n".join(
        [
            "https://bucket.s3.amazonaws.com/object"
            "?X-Amz-" + "Credential=AKIAEXAMPLE%2F20260619%2Fus-east-1%2Fs3%2Faws4_request"
            "&X-Amz-" + f"Signature={aws_signature}",
            "https://storage.googleapis.com/bucket/object"
            "?Google" + "AccessId=service@example.iam.gserviceaccount.com"
            "&X-Goog-" + f"Signature={google_signature}",
            "https://acct.blob.core.windows.net/container/blob?sv=2025-11-05&"
            "si" + f"g={azure_signature}",
        ]
    )

    result = redactor.redact_text(text)

    assert aws_signature not in result.value
    assert google_signature not in result.value
    assert azure_signature not in result.value
    assert "X-Amz-Signature=[REDACTED_SECRET]" in result.value
    assert "X-Goog-Signature=[REDACTED_SECRET]" in result.value
    assert "sig=[REDACTED_SECRET]" in result.value


def test_pgp_and_encrypted_private_keys_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    encrypted_key = (
        "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----\n"
        "FixtureToken000000000000000000000\n"
        "-----END " + "ENCRYPTED PRIVATE KEY-----"
    )
    pgp_key = (
        "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----\n"
        "FixtureToken000000000000000000000\n"
        "-----END " + "PGP PRIVATE KEY BLOCK-----"
    )

    result = redactor.redact_text(f"{encrypted_key}\n{pgp_key}")

    assert encrypted_key not in result.value
    assert pgp_key not in result.value
    assert result.value.count("[REDACTED_SECRET]") == 2


def test_prefixed_labeled_unknown_secret_is_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    unknown_token = "opaque-provider-token-without-known-prefix"

    result = redactor.redact_text(f"CLOUDFLARE_API_KEY={unknown_token}")

    assert unknown_token not in result.value
    assert result.value == "CLOUDFLARE_API_KEY=[REDACTED_SECRET]"


def test_authorization_header_value_is_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    bearer = "opaqueBearerTokenWithoutKnownPrefix"

    result = redactor.redact_text(f"Authorization: Bearer {bearer}")

    assert bearer not in result.value
    assert result.value == "Authorization: Bearer [REDACTED_SECRET]"


def test_connection_string_password_is_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic"))
    password = "db-password-without-known-prefix"

    result = redactor.redact_text(f"postgresql://user:{password}@localhost/app")

    assert password not in result.value
    assert result.value == "postgresql://user:[REDACTED_SECRET]@localhost/app"


def test_comma_separated_provider_api_keys_are_redacted() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="detect-secrets"))
    text = ", ".join(PROVIDER_FIXTURES.values())

    result = redactor.redact_text(text)

    for value in PROVIDER_FIXTURES.values():
        assert value not in result.value
    assert result.value.count("[REDACTED_SECRET]") >= len(PROVIDER_FIXTURES)


def test_gemini_key_is_fully_redacted_by_default() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="detect-secrets"))
    fake_gemini_key = PROVIDER_FIXTURES["gemini_api_key"]

    result = redactor.redact_text(f"GEMINI_API_KEY={fake_gemini_key}")

    assert fake_gemini_key not in result.value
    assert result.value == "GEMINI_API_KEY=[REDACTED_SECRET]"


def test_comma_separated_assignment_redacts_each_provider_key() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="detect-secrets"))
    values = [
        PROVIDER_FIXTURES["openai_key"],
        PROVIDER_FIXTURES["gemini_api_key"],
        PROVIDER_FIXTURES["anthropic_api_key"],
    ]

    result = redactor.redact_text(f"API_KEYS={','.join(values)}")

    for value in values:
        assert value not in result.value
    assert result.value.count("[REDACTED_SECRET]") >= len(values)


def test_detect_secrets_engine_redacts_api_key_assignment() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="detect-secrets"))

    result = redactor.redact_text(f"OPENAI_API_KEY={OPENAI_FAKE}")

    assert OPENAI_FAKE not in result.value
    assert any(name.startswith("detect_secrets:") for name in result.stats.rule_hits)


def test_detect_secrets_engine_does_not_redact_entropy_only_string() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="detect-secrets"))
    token_like_text = "value=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    result = redactor.redact_text(token_like_text)

    assert result.value == token_like_text
    assert result.stats.redactions == 0


def test_tail_rule_redacts_full_token() -> None:
    redactor = SecretRedactor(
        RedactionConfig(
            engine="basic",
            rules=[RuleConfig(type="exact", value="abcd1234", name="tail")],
        )
    )

    result = redactor.redact_text("token=pc_live_9999999999999999abcd1234")

    assert "9999999999999999abcd1234" not in result.value
    assert result.stats.rule_hits["tail"] == 1


def test_generic_assignment_preserves_key_name() -> None:
    redactor = SecretRedactor(RedactionConfig(engine="basic", redact_mode="full"))

    result = redactor.redact_text('password = "correct-horse-battery-staple"')

    assert "password" in result.value
    assert "correct-horse" not in result.value
    assert "[REDACTED_SECRET]" in result.value
