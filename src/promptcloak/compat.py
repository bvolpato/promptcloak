from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4


def responses_to_chat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    chat: dict[str, Any] = {
        "model": payload.get("model"),
        "messages": _responses_messages_to_chat(payload),
        "stream": bool(payload.get("stream", False)),
    }
    if payload.get("tools"):
        chat["tools"] = _responses_tools_to_chat(payload["tools"])
    if payload.get("tool_choice") in {"auto", "none", "required"}:
        chat["tool_choice"] = payload["tool_choice"]
    if "parallel_tool_calls" in payload:
        chat["parallel_tool_calls"] = payload["parallel_tool_calls"]
    for source, target in {
        "temperature": "temperature",
        "top_p": "top_p",
        "max_output_tokens": "max_tokens",
    }.items():
        if source in payload:
            chat[target] = payload[source]
    response_format = _response_format(payload.get("text"))
    if response_format:
        chat["response_format"] = response_format
    if chat["stream"]:
        chat["stream_options"] = {"include_usage": True}
    return {key: value for key, value in chat.items() if value is not None}


def chat_response_to_responses(payload: dict[str, Any]) -> dict[str, Any]:
    response_id = _response_id(payload)
    output = _chat_message_to_response_items(_chat_message(payload), response_id)
    return {
        "id": response_id,
        "object": "response",
        "status": "completed",
        "output": output,
        "usage": _responses_usage(payload.get("usage")),
        "end_turn": True,
    }


async def chat_stream_to_responses(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    state = _ChatStreamState()
    yield _sse(
        {
            "type": "response.created",
            "response": {"id": state.response_id, "status": "in_progress"},
        }
    )
    buffer = ""
    async for chunk in chunks:
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            raw, buffer = buffer.split("\n\n", 1)
            async for event in _chat_sse_event_to_responses(raw, state):
                yield event
    if buffer.strip():
        async for event in _chat_sse_event_to_responses(buffer, state):
            yield event
    for event in state.finish_events():
        yield event


class _ChatStreamState:
    def __init__(self) -> None:
        self.response_id = f"resp_{uuid4().hex}"
        self.message_id = f"msg_{uuid4().hex}"
        self.text = ""
        self.message_started = False
        self.tool_calls: dict[int, dict[str, Any]] = {}
        self.usage: dict[str, Any] | None = None
        self.finished = False

    def text_delta_events(self, delta: str) -> list[bytes]:
        events = []
        if not self.message_started:
            self.message_started = True
            events.append(
                _sse(
                    {
                        "type": "response.output_item.added",
                        "item": self.message_item(""),
                    }
                )
            )
        self.text += delta
        events.append(_sse({"type": "response.output_text.delta", "delta": delta}))
        return events

    def merge_tool_call_delta(self, delta: dict[str, Any]) -> None:
        index = int(delta.get("index", len(self.tool_calls)))
        tool_call = self.tool_calls.setdefault(
            index,
            {"id": delta.get("id") or f"call_{uuid4().hex}", "name": "", "arguments": ""},
        )
        if delta.get("id"):
            tool_call["id"] = delta["id"]
        function = delta.get("function") or {}
        if function.get("name"):
            tool_call["name"] += function["name"]
        if function.get("arguments"):
            tool_call["arguments"] += function["arguments"]

    def message_item(self, text: str) -> dict[str, Any]:
        return {
            "type": "message",
            "role": "assistant",
            "id": self.message_id,
            "content": [{"type": "output_text", "text": text}],
        }

    def tool_item(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function_call",
            "call_id": tool_call["id"],
            "name": tool_call["name"],
            "arguments": tool_call["arguments"],
        }

    def finish_events(self) -> list[bytes]:
        if self.finished:
            return []
        self.finished = True
        events = []
        output = []
        if self.message_started:
            item = self.message_item(self.text)
            output.append(item)
            events.append(_sse({"type": "response.output_item.done", "item": item}))
        for tool_call in self.tool_calls.values():
            item = self.tool_item(tool_call)
            output.append(item)
            events.append(_sse({"type": "response.output_item.done", "item": item}))
        events.append(
            _sse(
                {
                    "type": "response.completed",
                    "response": {
                        "id": self.response_id,
                        "status": "completed",
                        "output": output,
                        "usage": _responses_usage(self.usage),
                        "end_turn": True,
                    },
                }
            )
        )
        return events


async def _chat_sse_event_to_responses(
    raw: str, state: _ChatStreamState
) -> AsyncIterator[bytes]:
    data = "\n".join(
        line.removeprefix("data:").lstrip()
        for line in raw.splitlines()
        if line.startswith("data:")
    )
    if not data:
        return
    if data == "[DONE]":
        for event in state.finish_events():
            yield event
        return
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return
    if payload.get("usage"):
        state.usage = payload["usage"]
    for choice in payload.get("choices") or []:
        delta = choice.get("delta") or {}
        if delta.get("content"):
            for event in state.text_delta_events(delta["content"]):
                yield event
        for tool_delta in delta.get("tool_calls") or []:
            state.merge_tool_call_delta(tool_delta)


def _responses_messages_to_chat(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if payload.get("instructions"):
        messages.append({"role": "system", "content": payload["instructions"]})
    input_value = payload.get("input")
    if isinstance(input_value, str):
        messages.append({"role": "user", "content": input_value})
    elif isinstance(input_value, list):
        for item in input_value:
            messages.extend(_response_item_to_chat_messages(item))
    if not messages:
        messages.append({"role": "user", "content": ""})
    return messages


def _response_item_to_chat_messages(item: Any) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    kind = item.get("type", "message")
    if kind == "message":
        role = item.get("role") or "user"
        return [{"role": role, "content": _content_to_chat(item.get("content"))}]
    if kind in {"function_call", "custom_tool_call"}:
        name = _tool_name(item)
        arguments = item.get("arguments") or item.get("input") or "{}"
        return [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": item.get("call_id") or f"call_{uuid4().hex}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
        ]
    if kind in {"function_call_output", "custom_tool_call_output"}:
        return [
            {
                "role": "tool",
                "tool_call_id": item.get("call_id"),
                "content": _output_to_text(item.get("output")),
            }
        ]
    return []


def _content_to_chat(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts = []
    texts = []
    for item in content:
        if not isinstance(item, dict):
            texts.append(str(item))
            continue
        text = item.get("text")
        if item.get("type") in {"input_text", "output_text", "text"} and text is not None:
            texts.append(str(text))
            parts.append({"type": "text", "text": str(text)})
            continue
        image_url = item.get("image_url") or item.get("url")
        if image_url:
            parts.append({"type": "image_url", "image_url": image_url})
    if len(parts) == len(texts):
        return "\n".join(texts)
    return parts or "\n".join(texts)


def _output_to_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        texts = [
            str(item["text"])
            for item in output
            if isinstance(item, dict) and item.get("text") is not None
        ]
        return "\n".join(texts) if texts else json.dumps(output, separators=(",", ":"))
    return "" if output is None else json.dumps(output, separators=(",", ":"))


def _responses_tools_to_chat(tools: list[Any]) -> list[dict[str, Any]]:
    chat_tools = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function":
            chat_tools.append(_function_tool_to_chat(tool))
        elif tool.get("type") == "namespace":
            namespace = tool.get("name")
            for nested in tool.get("tools") or []:
                if isinstance(nested, dict) and nested.get("type") == "function":
                    chat_tools.append(_function_tool_to_chat(nested, namespace))
    return chat_tools


def _function_tool_to_chat(tool: dict[str, Any], namespace: str | None = None) -> dict[str, Any]:
    name = tool.get("name") or "tool"
    function = {
        "name": f"{namespace}__{name}" if namespace else name,
        "description": tool.get("description") or "",
        "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
    }
    if "strict" in tool:
        function["strict"] = tool["strict"]
    return {"type": "function", "function": function}


def _response_format(text_config: Any) -> dict[str, Any] | None:
    if not isinstance(text_config, dict):
        return None
    fmt = text_config.get("format")
    if not isinstance(fmt, dict):
        return None
    if fmt.get("type") != "json_schema":
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": fmt.get("name") or "response",
            "schema": fmt.get("schema") or {},
            "strict": bool(fmt.get("strict", False)),
        },
    }


def _chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            return message
    return {}


def _chat_message_to_response_items(
    message: dict[str, Any], response_id: str
) -> list[dict[str, Any]]:
    items = []
    content = message.get("content")
    if content:
        items.append(
            {
                "type": "message",
                "role": "assistant",
                "id": f"msg_{response_id}",
                "content": [{"type": "output_text", "text": content}],
            }
        )
    for tool_call in message.get("tool_calls") or []:
        function = tool_call.get("function") or {}
        items.append(
            {
                "type": "function_call",
                "call_id": tool_call.get("id") or f"call_{uuid4().hex}",
                "name": function.get("name") or "tool",
                "arguments": function.get("arguments") or "{}",
            }
        )
    return items


def _response_id(payload: dict[str, Any]) -> str:
    upstream_id = payload.get("id")
    if upstream_id:
        return f"resp_{upstream_id}"
    return f"resp_{uuid4().hex}"


def _responses_usage(usage: Any) -> dict[str, Any] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    total_tokens = usage.get("total_tokens") or input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_tokens,
    }


def _tool_name(item: dict[str, Any]) -> str:
    name = item.get("name") or "tool"
    namespace = item.get("namespace")
    return f"{namespace}__{name}" if namespace else name


def _sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()
