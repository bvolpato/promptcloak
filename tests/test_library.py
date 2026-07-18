from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, Field

from promptcloak import PromptCloak, redact_messages, redact_params, scan_params
from promptcloak.config import RedactionConfig, RuleConfig
from tests.fixtures import GEMINI_FAKE, OPENAI_FAKE


@dataclass(frozen=True)
class FixtureMessage:
    content: Any
    role: str = "human"

    def model_copy(self, update: dict[str, Any]) -> FixtureMessage:
        return replace(self, **update)


class FixturePydanticMessage(BaseModel):
    content: str
    additional_kwargs: dict[str, Any] = Field(default_factory=dict)


def test_redact_messages_filters_openai_dict_messages_without_mutating_original() -> None:
    messages = [{"role": "user", "content": f"OPENAI_API_KEY={OPENAI_FAKE}"}]

    redacted = redact_messages(messages)

    assert OPENAI_FAKE in messages[0]["content"]
    assert OPENAI_FAKE not in redacted[0]["content"]
    assert redacted[0]["content"] == "OPENAI_API_KEY=[REDACTED_SECRET]"


def test_redact_params_filters_litellm_style_kwargs() -> None:
    safe_kwargs = redact_params(
        model="openrouter/openai/gpt-5.5",
        messages=[{"role": "user", "content": f"GEMINI_API_KEY={GEMINI_FAKE}"}],
        temperature=0,
    )

    assert safe_kwargs["model"] == "openrouter/openai/gpt-5.5"
    assert safe_kwargs["temperature"] == 0
    assert GEMINI_FAKE not in safe_kwargs["messages"][0]["content"]
    assert safe_kwargs["messages"][0]["content"] == "GEMINI_API_KEY=[REDACTED_SECRET]"


def test_redact_messages_filters_langchain_tuple_messages() -> None:
    messages = [("human", f"token={OPENAI_FAKE}")]

    redacted = redact_messages(messages)

    assert redacted == [("human", "token=[REDACTED_SECRET]")]


def test_redact_messages_filters_langchain_message_objects() -> None:
    messages = [FixtureMessage(content=f"secret={GEMINI_FAKE}")]

    redacted = redact_messages(messages)

    assert isinstance(redacted[0], FixtureMessage)
    assert messages[0].content.endswith(GEMINI_FAKE)
    assert redacted[0].content == "secret=[REDACTED_SECRET]"


def test_redact_messages_scans_all_pydantic_message_fields() -> None:
    messages = [
        FixturePydanticMessage(
            content="hello",
            additional_kwargs={"tool_token": OPENAI_FAKE},
        )
    ]

    redacted = redact_messages(messages)

    assert messages[0].additional_kwargs["tool_token"] == OPENAI_FAKE
    assert redacted[0].additional_kwargs["tool_token"] == "[REDACTED_SECRET]"


def test_scan_params_returns_redaction_stats() -> None:
    result = scan_params(messages=[{"role": "user", "content": f"key {OPENAI_FAKE}"}])

    assert result.stats.redactions >= 1
    assert OPENAI_FAKE not in result.value["messages"][0]["content"]


def test_promptcloak_instance_uses_custom_rules() -> None:
    cloak = PromptCloak(
        RedactionConfig(
            engine="basic",
            rules=[RuleConfig(type="exact", value="abcd1234", name="tail")],
        )
    )

    result = cloak.scan_text("token=pc_live_000000000000abcd1234")

    assert "pc_live_000000000000abcd1234" not in result.value
    assert "[REDACTED_SECRET]" in result.value
    assert result.stats.rule_hits["tail"] == 1
