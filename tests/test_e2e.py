from __future__ import annotations

import json
import logging
import socket

import httpx
import pytest
import respx

from promptcloak.config import (
    AuditConfig,
    CompatConfig,
    RedactionConfig,
    RuleConfig,
    Settings,
    TargetConfig,
)
from promptcloak.proxy import create_app
from tests.fixtures import (
    CUSTOM_TAIL_SECRET,
    GEMINI_FAKE,
    OPENAI_FAKE,
    assert_header_absent,
    assert_no_fixture_values,
    complex_payload,
)


def _transport(settings: Settings) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=create_app(settings))


@pytest.mark.asyncio
@respx.mock
async def test_e2e_responses_request_redacts_nested_payload_and_audit_log(
    tmp_path,
) -> None:
    audit_file = tmp_path / "audit.jsonl"
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            api_key="upstream-token",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(
            engine="detect-secrets",
            rules=[RuleConfig(type="exact", value="abcd1234", name="custom-tail")],
        ),
        audit=AuditConfig(file=audit_file),
    )
    route = respx.post("https://upstream.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"id": "resp_fixture", "ok": True})
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post("/v1/responses", json=complex_payload())

    assert response.status_code == 200
    forwarded = route.calls.last.request
    forwarded_payload = json.loads(forwarded.content)
    assert_no_fixture_values(forwarded_payload)
    assert forwarded.headers["authorization"] == "Bearer upstream-token"
    assert_header_absent(forwarded.headers, "x-target-api-key")

    audit_events = [json.loads(line) for line in audit_file.read_text().splitlines()]
    assert audit_events[0]["event"] == "redaction"
    assert audit_events[0]["redactions"] >= 8
    assert_no_fixture_values(audit_events)


@pytest.mark.asyncio
@respx.mock
async def test_e2e_anthropic_messages_uses_x_api_key_and_dynamic_target() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://unused.example/v1",
            allowed_base_urls=["https://anthropic.example/v1"],
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="detect-secrets"),
    )
    route = respx.post("https://anthropic.example/v1/messages").mock(
        return_value=httpx.Response(200, json={"id": "msg_fixture"})
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                "X-Target-Base-URL": "https://anthropic.example/v1",
                "X-Target-API-Key": "upstream-token",
                "X-Target-API-Key-Header": "x-api-key",
            },
            json={"messages": [{"role": "user", "content": f"key={GEMINI_FAKE}"}]},
        )

    assert response.status_code == 200
    forwarded = route.calls.last.request
    assert forwarded.headers["x-api-key"] == "upstream-token"
    assert_header_absent(forwarded.headers, "authorization")
    assert_no_fixture_values(json.loads(forwarded.content))


@pytest.mark.asyncio
@respx.mock
async def test_e2e_text_body_redaction_handles_case_insensitive_content_type() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/raw").mock(
        return_value=httpx.Response(200, text="ok")
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/raw",
            headers={"Content-Type": "Text/Plain"},
            content=f"OPENAI_API_KEY={OPENAI_FAKE}",
        )

    assert response.status_code == 200
    assert_no_fixture_values(route.calls.last.request.content.decode())
    assert route.calls.last.request.content.decode() == "OPENAI_API_KEY=[REDACTED_SECRET]"


@pytest.mark.asyncio
async def test_e2e_target_url_userinfo_is_rejected() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        )
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-Base-URL": "https://user:pass@upstream.example/v1"},
            json={"input": "hello"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "target URL userinfo not allowed"


@pytest.mark.asyncio
async def test_e2e_target_url_invalid_port_is_rejected() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        )
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-Base-URL": "https://upstream.example:invalid/v1"},
            json={"input": "hello"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid target URL"


@pytest.mark.asyncio
async def test_e2e_target_allowlist_rejects_prefix_lookalike() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://allowed.example/v1",
            allowed_base_urls=["https://allowed.example/v1"],
            block_private_targets=False,
        )
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-Base-URL": "https://allowed.example/v1.evil"},
            json={"input": "hello"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "target URL not allowed"


@pytest.mark.asyncio
@respx.mock
async def test_e2e_public_dynamic_target_is_allowed_without_allowlist(monkeypatch) -> None:
    settings = Settings(target=TargetConfig(default_base_url="https://configured.example/v1"))
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )
    route = respx.post("https://dynamic.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-Base-URL": "https://dynamic.example/v1"},
            json={"input": "hello"},
        )

    assert response.status_code == 200
    assert route.called


@pytest.mark.asyncio
async def test_e2e_private_target_resolution_fails_closed(monkeypatch) -> None:
    settings = Settings(target=TargetConfig(default_base_url="https://configured.example/v1"))
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))],
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post("/v1/responses", json={"input": "hello"})

    assert response.status_code == 403
    assert response.json()["detail"] == "private target URL blocked"


@pytest.mark.asyncio
async def test_e2e_unresolved_target_is_rejected(monkeypatch) -> None:
    settings = Settings(target=TargetConfig(default_base_url="https://configured.example/v1"))

    def fail_resolution(*_args, **_kwargs):
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post("/v1/responses", json={"input": "hello"})

    assert response.status_code == 400
    assert response.json()["detail"] == "target host could not be resolved"


@pytest.mark.asyncio
async def test_e2e_allowlist_rejects_path_traversal() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://allowed.example/v1",
            allowed_base_urls=["https://allowed.example/v1"],
            block_private_targets=False,
        )
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/admin",
            headers={"X-Target-Base-URL": "https://allowed.example/v1/.."},
            json={"input": "hello"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "target URL not allowed"


@pytest.mark.asyncio
async def test_e2e_invalid_redaction_rules_header_is_rejected() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        )
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Redact-Extra-Rules": '{"type":"exact","value":"abcd1234"}'},
            json={"input": "hello"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid X-Redact-Extra-Rules header"


@pytest.mark.asyncio
@respx.mock
async def test_e2e_debug_headers_mask_redaction_rule_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    settings.server.debug_requests = True
    respx.post("https://upstream.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    with caplog.at_level(logging.WARNING, logger="promptcloak"):
        async with httpx.AsyncClient(
            transport=_transport(settings), base_url="http://proxy"
        ) as client:
            response = await client.post(
                "/v1/responses",
                headers={
                    "X-Redact-Extra-Rules": json.dumps(
                        [{"type": "exact", "value": "abcd1234", "name": "tail"}]
                    )
                },
                json={"input": f"token={CUSTOM_TAIL_SECRET}"},
            )

    assert response.status_code == 200
    event = next(
        json.loads(record.message)
        for record in caplog.records
        if '"event": "debug_request"' in record.message
    )
    assert event["headers"]["x-redact-extra-rules"] == "[REDACTED_HEADER]"
    assert_no_fixture_values(event["redacted_body"])


@pytest.mark.asyncio
@respx.mock
async def test_e2e_responses_to_chat_bridge_redacts_before_translation() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            api_key="upstream-token",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="detect-secrets"),
        compat=CompatConfig(responses_to_chat=True),
    )
    route = respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_fixture",
                "choices": [{"message": {"role": "assistant", "content": "redacted"}}],
            },
        )
    )

    async with httpx.AsyncClient(transport=_transport(settings), base_url="http://proxy") as client:
        response = await client.post("/v1/responses", json=complex_payload() | {"stream": False})

    assert response.status_code == 200
    assert_header_absent(route.calls.last.request.headers, "x-target-api-key")
    assert route.calls.last.request.headers["authorization"] == "Bearer upstream-token"
    assert_no_fixture_values(json.loads(route.calls.last.request.content))
    assert response.json()["output"][0]["content"][0]["text"] == "redacted"
