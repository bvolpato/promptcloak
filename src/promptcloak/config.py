from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from promptcloak.security import decrypt_text, load_key

CONFIG_DIR = Path.home() / ".config" / "promptcloak"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"
DEFAULT_KEY_PATH = CONFIG_DIR / "key"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str | None = None
    debug_requests: bool = False
    debug_max_body_chars: int = 20000


class TargetConfig(BaseModel):
    default_base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    api_key_header: Literal["authorization", "x-api-key"] = "authorization"
    forward_client_authorization: bool = False
    timeout_seconds: float = 180.0
    allowed_base_urls: list[str] = Field(default_factory=list)
    block_private_targets: bool = True

    @field_validator("default_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("target base URL must start with http:// or https://")
        return value


class RuleConfig(BaseModel):
    type: Literal["exact", "regex"]
    value: str
    name: str | None = None


class RedactionConfig(BaseModel):
    enabled: bool = True
    engine: Literal["detect-secrets", "basic"] = "detect-secrets"
    redact_mode: Literal["partial", "full"] = "full"
    placeholder: str = "[REDACTED_SECRET]"
    rules: list[RuleConfig] = Field(default_factory=list)
    encrypted: bool = False
    encrypted_rules: str | None = None
    scan_responses: bool = False


class AuditConfig(BaseModel):
    enabled: bool = True
    file: Path | None = None


class CompatConfig(BaseModel):
    responses_to_chat: bool = False


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    compat: CompatConfig = Field(default_factory=CompatConfig)


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _env_overrides() -> dict[str, Any]:
    mapping: dict[str, tuple[str, ...]] = {
        "PROMPTCLOAK_HOST": ("server", "host"),
        "PROMPTCLOAK_PORT": ("server", "port"),
        "PROMPTCLOAK_SERVER_API_KEY": ("server", "api_key"),
        "PROMPTCLOAK_DEBUG_REQUESTS": ("server", "debug_requests"),
        "PROMPTCLOAK_DEBUG_MAX_BODY_CHARS": ("server", "debug_max_body_chars"),
        "PROMPTCLOAK_TARGET_DEFAULT_BASE_URL": ("target", "default_base_url"),
        "PROMPTCLOAK_TARGET_BASE_URL": ("target", "default_base_url"),
        "PROMPTCLOAK_TARGET_API_KEY": ("target", "api_key"),
        "PROMPTCLOAK_TARGET_API_KEY_HEADER": ("target", "api_key_header"),
        "PROMPTCLOAK_FORWARD_CLIENT_AUTHORIZATION": (
            "target",
            "forward_client_authorization",
        ),
        "PROMPTCLOAK_TARGET_TIMEOUT_SECONDS": ("target", "timeout_seconds"),
        "PROMPTCLOAK_REDACTION_ENABLED": ("redaction", "enabled"),
        "PROMPTCLOAK_REDACTION_ENGINE": ("redaction", "engine"),
        "PROMPTCLOAK_REDACTION_MODE": ("redaction", "redact_mode"),
        "PROMPTCLOAK_SCAN_RESPONSES": ("redaction", "scan_responses"),
        "PROMPTCLOAK_RESPONSES_TO_CHAT": ("compat", "responses_to_chat"),
    }
    data: dict[str, Any] = {}
    for env_name, path in mapping.items():
        if env_name not in os.environ:
            continue
        target = data
        for segment in path[:-1]:
            target = target.setdefault(segment, {})
        raw: str = os.environ[env_name]
        if raw.lower() in {"true", "false"}:
            value: Any = raw.lower() == "true"
        elif raw.isdigit():
            value = int(raw)
        else:
            try:
                value = float(raw)
            except ValueError:
                value = raw
        target[path[-1]] = value
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded or {}


def _decrypt_rules_if_needed(settings: Settings, key_path: Path) -> Settings:
    redaction = settings.redaction
    if not redaction.encrypted or not redaction.encrypted_rules:
        return settings
    key = load_key(key_path)
    decrypted = decrypt_text(redaction.encrypted_rules, key)
    rules = yaml.safe_load(decrypted) or []
    redaction.rules = [RuleConfig.model_validate(rule) for rule in rules]
    return settings


def load_settings(config_path: Path | None = None, key_path: Path | None = None) -> Settings:
    path = config_path or Path(os.getenv("PROMPTCLOAK_CONFIG", DEFAULT_CONFIG_PATH))
    key_file = key_path or Path(os.getenv("PROMPTCLOAK_KEY_FILE", DEFAULT_KEY_PATH))
    data = _deep_update(_load_yaml(path), _env_overrides())
    settings = Settings.model_validate(data)
    return _decrypt_rules_if_needed(settings, key_file)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def config_template(target_base_url: str, target_api_key_env: str) -> str:
    return yaml.safe_dump(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 8000,
                "api_key": None,
                "debug_requests": False,
                "debug_max_body_chars": 20000,
            },
            "target": {
                "default_base_url": target_base_url,
                "api_key": f"${{{target_api_key_env}}}",
                "api_key_header": "authorization",
                "forward_client_authorization": False,
                "timeout_seconds": 180,
                "allowed_base_urls": [],
                "block_private_targets": True,
            },
            "redaction": {
                "enabled": True,
                "engine": "detect-secrets",
                "redact_mode": "full",
                "encrypted": False,
                "scan_responses": False,
                "rules": [
                    {
                        "type": "exact",
                        "value": "abcd1234",
                        "name": "example-tail-only",
                    },
                    {
                        "type": "regex",
                        "value": "sk-[A-Za-z0-9_-]{20,}",
                        "name": "openai-style-token",
                    },
                ],
            },
            "audit": {"enabled": True, "file": None},
            "compat": {"responses_to_chat": False},
        },
        sort_keys=False,
    )


def expand_env_values(data: Any) -> Any:
    if isinstance(data, dict):
        return {key: expand_env_values(value) for key, value in data.items()}
    if isinstance(data, list):
        return [expand_env_values(value) for value in data]
    if isinstance(data, str) and data.startswith("${") and data.endswith("}"):
        return os.getenv(data[2:-1])
    return data
