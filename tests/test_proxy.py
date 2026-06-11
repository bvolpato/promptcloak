import json
import logging

import httpx
import pytest
import respx

from promptcloak.config import CompatConfig, RedactionConfig, ServerConfig, Settings, TargetConfig
from promptcloak.proxy import create_app
from tests.fixtures import OPENAI_FAKE


@pytest.mark.asyncio
@respx.mock
async def test_proxy_redacts_and_forwards_json() -> None:
    settings = Settings(
        server=ServerConfig(api_key="local-token"),
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            api_key="upstream-token",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer local-token"},
            json={
                "model": "test",
                "messages": [{"role": "user", "content": f"key {OPENAI_FAKE}"}],
            },
        )

    assert response.status_code == 200
    assert route.called
    forwarded = route.calls.last.request
    assert forwarded.headers["authorization"] == "Bearer upstream-token"
    assert OPENAI_FAKE not in forwarded.content.decode()


@pytest.mark.asyncio
@respx.mock
async def test_x_target_base_url_overrides_target() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://default.example/v1",
            allowed_base_urls=["https://alt.example/v1"],
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://alt.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"id": "resp_1"})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-Base-URL": "https://alt.example/v1"},
            json={"input": "hello"},
        )

    assert response.status_code == 200
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_per_request_redaction_rules() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1", block_private_targets=False
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"X-Redact-Extra-Rules": '[{"type":"exact","value":"abcd1234","name":"tail"}]'},
            json={"messages": [{"role": "user", "content": "token pc_live_000000abcd1234"}]},
        )

    assert response.status_code == 200
    assert "pc_live_000000abcd1234" not in route.calls.last.request.content.decode()


@pytest.mark.asyncio
async def test_proxy_auth_rejects_wrong_key() -> None:
    app = create_app(Settings(server=ServerConfig(api_key="local-token")))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer wrong"},
            json={"messages": []},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_client_auth_headers_not_forwarded_without_target_opt_in() -> None:
    settings = Settings(
        server=ServerConfig(api_key="local-token"),
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer local-token", "X-API-Key": "client-key"},
            json={"input": "hello"},
        )

    assert response.status_code == 200
    assert "authorization" not in route.calls.last.request.headers
    assert "x-api-key" not in route.calls.last.request.headers


@pytest.mark.asyncio
@respx.mock
async def test_client_authorization_forwarded_only_when_opted_in() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
            forward_client_authorization=True,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer client-token"},
            json={"input": "hello"},
        )

    assert response.status_code == 200
    assert route.calls.last.request.headers["authorization"] == "Bearer client-token"


@pytest.mark.asyncio
@respx.mock
async def test_target_api_key_header_sets_upstream_authorization() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-API-Key": "upstream-token"},
            json={"input": "hello"},
        )

    assert response.status_code == 200
    forwarded = route.calls.last.request
    assert forwarded.headers["authorization"] == "Bearer upstream-token"
    assert "x-target-api-key" not in forwarded.headers


@pytest.mark.asyncio
@respx.mock
async def test_target_api_key_header_can_set_upstream_x_api_key() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            api_key_header="x-api-key",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/messages").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/messages",
            headers={"X-Target-API-Key": "upstream-token"},
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    forwarded = route.calls.last.request
    assert forwarded.headers["x-api-key"] == "upstream-token"
    assert "authorization" not in forwarded.headers


@pytest.mark.asyncio
@respx.mock
async def test_target_api_key_header_can_be_overridden_per_request() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/messages").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                "X-Target-API-Key": "upstream-token",
                "X-Target-API-Key-Header": "x-api-key",
            },
            json={"messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 200
    assert route.calls.last.request.headers["x-api-key"] == "upstream-token"


@pytest.mark.asyncio
async def test_invalid_target_api_key_header_is_rejected() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        )
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                "X-Target-API-Key": "upstream-token",
                "X-Target-API-Key-Header": "invalid-header",
            },
            json={"messages": []},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_target_api_key_header_overrides_configured_target_key() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            api_key="configured-token",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/responses").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Target-API-Key": "header-token"},
            json={"input": "hello"},
        )

    assert response.status_code == 200
    assert route.calls.last.request.headers["authorization"] == "Bearer header-token"


@pytest.mark.asyncio
@respx.mock
async def test_debug_requests_log_raw_and_redacted_bodies(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        server=ServerConfig(debug_requests=True),
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
    )
    route = respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    with caplog.at_level(logging.WARNING, logger="promptcloak"):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"X-Target-API-Key": "upstream-token"},
                json={"messages": [{"role": "user", "content": f"key {OPENAI_FAKE}"}]},
            )

    assert response.status_code == 200
    assert route.called
    events = [
        json.loads(record.message)
        for record in caplog.records
        if '"event": "debug_request"' in record.message
    ]
    assert len(events) == 1
    event = events[0]
    assert event["redactions"] >= 1
    assert OPENAI_FAKE in event["raw_body"]
    assert OPENAI_FAKE not in event["redacted_body"]
    assert "[REDACTED_SECRET]" in event["redacted_body"]
    assert event["headers"]["x-target-api-key"] == "[REDACTED_HEADER]"


@pytest.mark.asyncio
@respx.mock
async def test_responses_to_chat_bridge_rewrites_request_and_response() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            api_key="upstream-token",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
        compat=CompatConfig(responses_to_chat=True),
    )
    route = respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_fixture",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "gpt-5.5",
                "instructions": "be terse",
                "stream": False,
                "input": [{"type": "message", "role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 200
    forwarded = json.loads(route.calls.last.request.content)
    assert forwarded["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hello"},
    ]
    assert response.json()["output"][0]["content"][0]["text"] == "ok"
    assert response.json()["usage"]["total_tokens"] == 5


@pytest.mark.asyncio
@respx.mock
async def test_responses_to_chat_bridge_streams_responses_events() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
        compat=CompatConfig(responses_to_chat=True),
    )
    route = respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            content=(
                b'data: {"id":"chatcmpl_fixture","choices":[{"delta":{"content":"he"}}]}\n\n'
                b'data: {"id":"chatcmpl_fixture","choices":[{"delta":{"content":"llo"}}],'
                b'"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
                b"data: [DONE]\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        )
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "gpt-5.5", "stream": True, "input": "hello"},
        )

    assert response.status_code == 200
    assert route.called
    forwarded = json.loads(route.calls.last.request.content)
    assert forwarded["stream"] is True
    assert forwarded["stream_options"] == {"include_usage": True}
    body = response.text
    assert "response.output_item.added" in body
    assert "response.output_text.delta" in body
    assert "response.output_item.done" in body
    assert "response.completed" in body
    assert "hello" in body


@pytest.mark.asyncio
@respx.mock
async def test_responses_to_chat_bridge_maps_chat_tool_calls() -> None:
    settings = Settings(
        target=TargetConfig(
            default_base_url="https://upstream.example/v1",
            block_private_targets=False,
        ),
        redaction=RedactionConfig(engine="basic"),
        compat=CompatConfig(responses_to_chat=True),
    )
    respx.post("https://upstream.example/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl_tool",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_fixture",
                                    "type": "function",
                                    "function": {
                                        "name": "exec_command",
                                        "arguments": '{"cmd":"pwd"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )
    )
    transport = httpx.ASGITransport(app=create_app(settings))

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "gpt-5.5",
                "input": "run pwd",
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "run command",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )

    item = response.json()["output"][0]
    assert item == {
        "type": "function_call",
        "call_id": "call_fixture",
        "name": "exec_command",
        "arguments": '{"cmd":"pwd"}',
    }
