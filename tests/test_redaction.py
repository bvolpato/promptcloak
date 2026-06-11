from promptcloak.config import RedactionConfig, RuleConfig
from promptcloak.redaction import SecretRedactor
from tests.fixtures import OPENAI_FAKE, PROVIDER_FIXTURES


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
