import tomllib
from pathlib import Path

import yaml

from promptcloak.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_compose_binds_proxy_to_loopback() -> None:
    data = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    assert data["services"]["promptcloak"]["ports"] == ["127.0.0.1:8000:8000"]


def test_openrouter_promptcloak_example_is_valid() -> None:
    data = yaml.safe_load((ROOT / "examples" / "promptcloak-openrouter.config.yaml").read_text())
    settings = Settings.model_validate(data)

    assert settings.target.default_base_url == "https://openrouter.ai/api/v1"
    assert settings.target.api_key is None
    assert settings.target.forward_client_authorization is True
    assert settings.target.allowed_base_urls == ["https://openrouter.ai/api/v1"]
    assert settings.compat.responses_to_chat is True


def test_codex_openrouter_profile_uses_env_key_and_local_proxy() -> None:
    data = tomllib.loads(
        (ROOT / "examples" / "codex-openrouter-promptcloak.config.toml").read_text()
    )
    provider = data["model_providers"]["promptcloak-openrouter"]

    assert data["model_provider"] == "promptcloak-openrouter"
    assert provider["base_url"] == "http://127.0.0.1:8000/v1"
    assert provider["env_key"] == "OPENROUTER_API_KEY"
    assert provider["wire_api"] == "responses"
