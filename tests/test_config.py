import pytest
from pydantic import ValidationError

from promptcloak.config import RuleConfig, TargetConfig, load_settings


def test_server_api_key_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PROMPTCLOAK_SERVER_API_KEY", "local-token")
    monkeypatch.setenv("PROMPTCLOAK_DEBUG_REQUESTS", "true")
    monkeypatch.setenv("PROMPTCLOAK_DEBUG_MAX_BODY_CHARS", "1234")
    monkeypatch.setenv("PROMPTCLOAK_TARGET_API_KEY", "upstream-token")
    monkeypatch.setenv("PROMPTCLOAK_TARGET_API_KEY_HEADER", "x-api-key")
    monkeypatch.setenv("PROMPTCLOAK_TARGET_BASE_URL", "https://upstream.example/v1")
    monkeypatch.setenv("PROMPTCLOAK_RESPONSES_TO_CHAT", "true")

    settings = load_settings(tmp_path / "missing.yaml")

    assert settings.server.api_key == "local-token"
    assert settings.server.debug_requests is True
    assert settings.server.debug_max_body_chars == 1234
    assert settings.target.api_key == "upstream-token"
    assert settings.target.api_key_header == "x-api-key"
    assert settings.target.default_base_url == "https://upstream.example/v1"
    assert settings.compat.responses_to_chat is True


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "ftp://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example/v1?key=value",
        "https://provider.example/v1#fragment",
        "https://provider.example:invalid/v1",
    ],
)
def test_target_base_urls_reject_ambiguous_values(url: str) -> None:
    with pytest.raises(ValidationError):
        TargetConfig(default_base_url=url)


def test_exact_rules_require_safe_tail_length() -> None:
    with pytest.raises(ValidationError):
        RuleConfig(type="exact", value="short")


def test_rule_names_are_bounded_log_labels() -> None:
    with pytest.raises(ValidationError):
        RuleConfig(type="regex", value="fixture", name="not a safe label")
