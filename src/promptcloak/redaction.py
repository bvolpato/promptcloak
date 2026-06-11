from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from promptcloak.config import RedactionConfig, RuleConfig

MASK = "[REDACTED_SECRET]"


BUILTIN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openrouter_key", re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("atlassian_api_token", re.compile(r"\bATATT3xFfGF0[A-Za-z0-9_-]{20,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{20,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("gemini_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]+?-----END "
            r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
        ),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|pwd|token|access[_-]?token)"
            r"(\s*[:=]\s*)([\"']?)([^\"'\s,;]{8,})([\"']?)"
        ),
    ),
]


@dataclass
class RedactionStats:
    redactions: int = 0
    rule_hits: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, count: int) -> None:
        if count <= 0:
            return
        self.redactions += count
        self.rule_hits[name] = self.rule_hits.get(name, 0) + count


@dataclass
class RedactionResult:
    value: Any
    stats: RedactionStats


class SecretRedactor:
    def __init__(self, config: RedactionConfig):
        self.config = config
        self.placeholder = config.placeholder or MASK
        self._custom_patterns = self._compile_custom_patterns(config.rules)

    def redact_payload(self, payload: Any) -> RedactionResult:
        stats = RedactionStats()
        if not self.config.enabled:
            return RedactionResult(payload, stats)
        return RedactionResult(self._walk(payload, stats), stats)

    def redact_text(self, text: str) -> RedactionResult:
        stats = RedactionStats()
        if not self.config.enabled:
            return RedactionResult(text, stats)
        return RedactionResult(self._redact_string(text, stats), stats)

    def _compile_custom_patterns(
        self, rules: list[RuleConfig]
    ) -> list[tuple[str, re.Pattern[str]]]:
        patterns: list[tuple[str, re.Pattern[str]]] = []
        for index, rule in enumerate(rules):
            name = rule.name or f"{rule.type}_{index}"
            if rule.type == "regex":
                patterns.append((name, re.compile(rule.value)))
                continue
            if len(rule.value) <= 16:
                tail = re.escape(rule.value)
                patterns.append((name, re.compile(rf"\b[A-Za-z0-9_./+=-]{{8,}}{tail}\b")))
            else:
                patterns.append((name, re.compile(re.escape(rule.value))))
        return patterns

    def _walk(self, value: Any, stats: RedactionStats) -> Any:
        if isinstance(value, str):
            return self._redact_string(value, stats)
        if isinstance(value, list):
            return [self._walk(item, stats) for item in value]
        if isinstance(value, tuple):
            return tuple(self._walk(item, stats) for item in value)
        if isinstance(value, Mapping):
            return {key: self._walk(item, stats) for key, item in value.items()}
        return value

    def _redact_string(self, value: str, stats: RedactionStats) -> str:
        original = value
        if self.config.engine == "detect-secrets":
            value = self._run_detect_secrets(value, stats)
        for name, pattern in self._custom_patterns:
            value, count = self._sub_pattern(pattern, value)
            stats.add(name, count)
        for name, pattern in BUILTIN_PATTERNS:
            value, count = self._sub_pattern(pattern, value)
            stats.add(name, count)
        if value != original and self.config.redact_mode == "partial":
            return value
        return value

    def _run_detect_secrets(self, value: str, stats: RedactionStats) -> str:
        if not value.strip():
            return value
        from detect_secrets import SecretsCollection
        from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class
        from detect_secrets.settings import transient_settings

        temp_file_name = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(value.encode("utf-8"))
                temp_file_name = temp_file.name
            plugin_config = [
                {"name": plugin_type.__name__}
                for plugin_type in get_mapping_from_secret_type_to_class().values()
                if plugin_type.__name__ not in {"Base64HighEntropyString", "HexHighEntropyString"}
            ]
            with transient_settings({"plugins_used": plugin_config}):
                secrets = SecretsCollection()
                secrets.scan_file(temp_file_name)
        finally:
            with suppress(OSError):
                os.remove(temp_file_name)

        for file_name in secrets.files:
            for found_secret in secrets[file_name]:
                secret_value = getattr(found_secret, "secret_value", None)
                if not secret_value:
                    continue
                value, count = self._replace_detected_secret(secret_value, value)
                stats.add(f"detect_secrets:{found_secret.type}", count)
        return value

    def _replace_detected_secret(self, secret_value: str, value: str) -> tuple[str, int]:
        if "," not in secret_value:
            return re.subn(re.escape(secret_value), self._replacement, value)

        total = 0
        for segment in secret_value.split(","):
            candidate = segment.strip().strip("\"'")
            if not candidate:
                continue
            value, count = re.subn(re.escape(candidate), self._replacement, value)
            total += count

        if total:
            return value, total
        return re.subn(re.escape(secret_value), self._replacement, value)

    def _sub_pattern(self, pattern: re.Pattern[str], value: str) -> tuple[str, int]:
        if pattern.pattern.startswith("(?i)\\b(api"):
            return pattern.subn(
                lambda match: (
                    f"{match.group(1)}{match.group(2)}{match.group(3)}"
                    f"{self.placeholder}{match.group(5)}"
                ),
                value,
            )
        return pattern.subn(self._replacement, value)

    def _replacement(self, match: re.Match[str]) -> str:
        secret = match.group(0)
        if self.config.redact_mode == "full" or len(secret) <= 12:
            return self.placeholder
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]
        return f"{secret[:4]}...{secret[-4:]}:{digest}"
