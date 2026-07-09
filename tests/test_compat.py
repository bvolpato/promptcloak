from __future__ import annotations

import json

import pytest

from promptcloak.compat import chat_stream_to_responses


async def _collect(parts: list[bytes]) -> str:
    async def chunks():
        for part in parts:
            yield part

    return b"".join([chunk async for chunk in chat_stream_to_responses(chunks())]).decode()


def _events(stream: str) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in stream.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_chat_stream_preserves_utf8_split_across_chunks() -> None:
    raw = (
        "data: "
        + json.dumps(
            {"choices": [{"delta": {"content": "😀"}}]},
            ensure_ascii=False,
        )
        + "\n\ndata: [DONE]\n\n"
    ).encode()
    split = raw.index("😀".encode()) + 2

    output = await _collect([raw[:split], raw[split:]])

    deltas = [event["delta"] for event in _events(output) if event["type"].endswith(".delta")]
    assert deltas == ["😀"]


@pytest.mark.asyncio
async def test_chat_stream_accepts_crlf_events_split_between_chunks() -> None:
    raw = b'data: {"choices":[{"delta":{"content":"hello"}}]}\r\n\r\ndata: [DONE]\r\n\r\n'
    split = raw.index(b"\r\n") + 1

    output = await _collect([raw[:split], raw[split:]])

    deltas = [event["delta"] for event in _events(output) if event["type"].endswith(".delta")]
    assert deltas == ["hello"]
    assert any(event["type"] == "response.completed" for event in _events(output))
