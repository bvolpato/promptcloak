from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from promptcloak.config import RedactionConfig, RuleConfig

MASK = "[REDACTED_SECRET]"

SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(?:^|[_.-])(?:api[_-]?keys?|client[_-]?secrets?|secrets?|passwords?|passwd|"
    r"pwd|tokens?|access[_-]?tokens?|refresh[_-]?tokens?|id[_-]?tokens?|auth|"
    r"authorization|auth[_-]?tokens?|session[_-]?tokens?|private[_-]?keys?|"
    r"credentials?|webhook[_-]?urls?|x[_-]?api[_-]?key|api[_-]?key|x[_-]?auth[_-]?key|"
    r"x[_-]?auth[_-]?token|cf[_-]?access[_-]?token|cloudflare[_-]?api[_-]?"
    r"(?:key|token)|signed[_-]?urls?|presigned[_-]?urls?|sas[_-]?tokens?|"
    r"dockerconfigjson|signature|sig)(?:$|[_.-])"
)

BUILTIN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openrouter_key", re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b")),
    ("minimax_key", re.compile(r"\bsk-cp-[A-Za-z0-9_-]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("fireworks_key", re.compile(r"\bfw_[A-Za-z0-9_-]{20,}\b")),
    ("xai_key", re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("atlassian_api_token", re.compile(r"\bATATT3xFfGF0[A-Za-z0-9_-]{20,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{20,}\b")),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("aws_access_key_extended", re.compile(r"\b(?:A3T[A-Z0-9]|ABIA|ACCA)[A-Z2-7]{16}\b")),
    ("aws_bedrock_api_key", re.compile(r"\bABSK[A-Za-z0-9+/]{80,}={0,2}\b")),
    ("gemini_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("google_oauth_token", re.compile(r"\bya29\.[A-Za-z0-9._-]{20,}\b")),
    ("onepassword_service_account_token", re.compile(r"\bops_eyJ[A-Za-z0-9+/]{120,}={0,3}\b")),
    ("age_secret_key", re.compile(r"\bAGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}\b")),
    ("databricks_api_token", re.compile(r"\bdapi[a-f0-9]{32}(?:-\d)?\b")),
    ("digitalocean_token", re.compile(r"\bd(?:op|oo|or)_v1_[a-f0-9]{64}\b")),
    ("huggingface_token", re.compile(r"\b(?:hf_|api_org_)[A-Za-z0-9]{34,}\b")),
    ("linear_api_key", re.compile(r"\blin_api_[A-Za-z0-9]{40}\b")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("pypi_upload_token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,1000}\b")),
    ("sendgrid_token", re.compile(r"\bSG\.[A-Za-z0-9_.=-]{66}\b")),
    (
        "slack_webhook",
        re.compile(
            r"\bhttps?://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9+/]{43,80}\b"
        ),
    ),
    ("telegram_bot_token", re.compile(r"\b[0-9]{5,16}:A[A-Za-z0-9_-]{34}\b")),
    ("twilio_api_key", re.compile(r"\bSK[0-9a-fA-F]{32}\b")),
    ("vault_token", re.compile(r"\bhv[bs]\.[A-Za-z0-9_-]{80,300}\b")),
    ("shopify_token", re.compile(r"\bshp(?:at|ca|pa|ss)_[a-fA-F0-9]{32}\b")),
    ("sentry_token", re.compile(r"\bsntry[su]_[A-Za-z0-9]{40,}\b")),
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
            r"[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
        ),
    ),
    (
        "pgp_private_key",
        re.compile(
            r"-----BEGIN PGP "
            r"PRIVATE KEY BLOCK-----[\s\S]+?-----END PGP "
            r"PRIVATE KEY BLOCK-----"
        ),
    ),
    (
        "signed_url_query_param",
        re.compile(
            r"(?i)([?&](?:x-amz-signature|x-amz-credential|x-amz-security-token|"
            r"x-goog-signature|x-goog-credential|googleaccessid|signature|sig)=)"
            r"([^&#\s]+)"
        ),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b([A-Za-z0-9_.-]*(?:api[_-]?keys?|client[_-]?secrets?|"
            r"secrets?|passwords?|passwd|pwd|tokens?|access[_-]?tokens?|"
            r"refresh[_-]?tokens?|id[_-]?tokens?|auth[_-]?tokens?|session[_-]?tokens?|"
            r"private[_-]?keys?|credentials?|webhook[_-]?urls?)[A-Za-z0-9_.-]*)"
            r"(\s*[:=]\s*)([\"']?)([^\"'\s;\[\]]{8,})([\"']?)"
        ),
    ),
    (
        "auth_header",
        re.compile(
            r"(?i)\b((?:authorization|proxy-authorization|x-api-key|api-key|x-auth-token|"
            r"x-auth-key|cf-access-token)"
            r"\s*[:=]\s*(?:(?:bearer|token|basic|key)\s+)?)([A-Za-z0-9._~+/=-]{8,})"
        ),
    ),
    (
        "url_credentials",
        re.compile(
            r"\b((?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
            r"[^:\s/@]+:)([^@\s/]+)(@)"
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
            return {
                key: (
                    self._redact_sensitive_field(item, stats)
                    if self._is_sensitive_field(key)
                    else self._walk(item, stats)
                )
                for key, item in value.items()
            }
        return value

    def _is_sensitive_field(self, key: Any) -> bool:
        if not isinstance(key, str):
            return False
        return SENSITIVE_FIELD_RE.search(key) is not None

    def _redact_sensitive_field(self, value: Any, stats: RedactionStats) -> Any:
        if isinstance(value, str):
            if len(value.strip()) < 8:
                return value
            stats.add("sensitive_field", 1)
            return self.placeholder
        if isinstance(value, list):
            return [self._redact_sensitive_field(item, stats) for item in value]
        if isinstance(value, tuple):
            return tuple(self._redact_sensitive_field(item, stats) for item in value)
        if isinstance(value, Mapping):
            return {key: self._redact_sensitive_field(item, stats) for key, item in value.items()}
        return value

    def _redact_string(self, value: str, stats: RedactionStats) -> str:
        original = value
        if self.config.engine == "detect-secrets":
            value = self._run_detect_secrets(value, stats)
        for name, pattern in self._custom_patterns:
            value, count = self._sub_pattern(name, pattern, value)
            stats.add(name, count)
        for name, pattern in BUILTIN_PATTERNS:
            value, count = self._sub_pattern(name, pattern, value)
            stats.add(name, count)
        if value != original and self.config.redact_mode == "partial":
            return value
        return value

    def _run_detect_secrets(self, value: str, stats: RedactionStats) -> str:
        if not value.strip():
            return value
        from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class
        from detect_secrets.core.scan import scan_line
        from detect_secrets.settings import transient_settings
        from detect_secrets.transformers import get_transformed_file

        plugin_config = [
            {"name": plugin_type.__name__}
            for plugin_type in get_mapping_from_secret_type_to_class().values()
            if plugin_type.__name__ not in {"Base64HighEntropyString", "HexHighEntropyString"}
        ]
        source = _PromptText(value)
        lines = get_transformed_file(source) or value.splitlines()
        source.seek(0)
        eager_lines = get_transformed_file(source, use_eager_transformers=True) or []
        with transient_settings({"plugins_used": plugin_config}):
            found_secrets = [secret for line in lines for secret in scan_line(line)]
            if not found_secrets:
                found_secrets = [secret for line in eager_lines for secret in scan_line(line)]

        for found_secret in found_secrets:
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

    def _sub_pattern(self, name: str, pattern: re.Pattern[str], value: str) -> tuple[str, int]:
        if name == "assigned_secret":
            return pattern.subn(
                lambda match: (
                    f"{match.group(1)}{match.group(2)}{match.group(3)}"
                    f"{self.placeholder}{match.group(5)}"
                ),
                value,
            )
        if name == "auth_header":
            return pattern.subn(lambda match: f"{match.group(1)}{self.placeholder}", value)
        if name == "signed_url_query_param":
            return pattern.subn(lambda match: f"{match.group(1)}{self.placeholder}", value)
        if name == "url_credentials":
            return pattern.subn(
                lambda match: f"{match.group(1)}{self.placeholder}{match.group(3)}", value
            )
        return pattern.subn(self._replacement, value)

    def _replacement(self, match: re.Match[str]) -> str:
        secret = match.group(0)
        if self.config.redact_mode == "full" or len(secret) <= 12:
            return self.placeholder
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]
        return f"{secret[:4]}...{secret[-4:]}:{digest}"


class _PromptText(io.StringIO):
    name = "promptcloak-input"
