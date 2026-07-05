from __future__ import annotations

import ipaddress
import json
import logging
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from promptcloak.audit import AuditLogger
from promptcloak.compat import (
    chat_response_to_responses,
    chat_stream_to_responses,
    responses_to_chat_payload,
)
from promptcloak.config import RuleConfig, Settings, expand_env_values, get_settings, load_settings
from promptcloak.redaction import RedactionStats, SecretRedactor
from promptcloak.version import __version__

logger = logging.getLogger("promptcloak")

DROP_REQUEST_HEADERS = {
    "content-length",
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "upgrade",
}
DROP_RESPONSE_HEADERS = {
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "upgrade",
}
SENSITIVE_DEBUG_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-target-api-key",
    "x-target-authorization",
}
CLIENT_AUTH_HEADERS = {"authorization", "x-api-key", "x-auth-token"}


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    expanded = Settings.model_validate(expand_env_values(resolved.model_dump()))

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        timeout = httpx.Timeout(expanded.target.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            _app.state.client = client
            yield

    app = FastAPI(
        title="PromptCloak",
        version=__version__,
        summary="Local OpenAI-compatible proxy that redacts secrets before forwarding requests.",
        lifespan=lifespan,
    )
    app.state.settings = expanded
    app.state.redactor = SecretRedactor(expanded.redaction)
    app.state.audit = AuditLogger(expanded.audit)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "redaction": expanded.redaction.enabled,
            "engine": expanded.redaction.engine,
            "telemetry": False,
        }

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def forward(path: str, request: Request) -> Response:
        return await forward_request(request, "/" + path)

    return app


async def forward_request(request: Request, path: str) -> Response:
    settings: Settings = request.app.state.settings
    _check_proxy_auth(request, settings)
    target_path = path
    target_url = _target_url(request, target_path, settings)
    _validate_target(target_url, settings)

    body = await request.body()
    redactor = _redactor_for_request(request, settings)
    audit: AuditLogger = request.app.state.audit
    content = body
    stats = RedactionStats()
    json_payload: Any | None = None

    if body and _is_json_request(request):
        try:
            json_payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid JSON request body") from None
        result = redactor.redact_payload(json_payload)
        json_payload = result.value
        stats = result.stats
        audit.redaction(path, result.stats)
        content = json.dumps(json_payload, separators=(",", ":")).encode("utf-8")
    elif body and _is_text_request(request):
        result = redactor.redact_text(body.decode("utf-8", errors="replace"))
        stats = result.stats
        audit.redaction(path, result.stats)
        content = result.value.encode("utf-8")

    compat_responses_to_chat = _should_bridge_responses_to_chat(request, path, settings)
    if compat_responses_to_chat:
        if not isinstance(json_payload, dict):
            raise HTTPException(
                status_code=400, detail="responses-to-chat bridge requires JSON body"
            )
        target_path = "/v1/chat/completions"
        target_url = _target_url(request, target_path, settings)
        _validate_target(target_url, settings)
        content = json.dumps(responses_to_chat_payload(json_payload), separators=(",", ":")).encode(
            "utf-8"
        )

    _debug_request(request, path, target_url, body, content, stats, settings)

    headers = _forward_headers(request, settings)
    client, close_client = _client_for_request(request, settings)

    try:
        upstream_request = client.build_request(
            request.method,
            target_url,
            content=content,
            headers=headers,
            params=request.query_params,
        )
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        if close_client:
            await client.aclose()
        raise HTTPException(status_code=502, detail=f"upstream request failed: {exc}") from exc

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in DROP_RESPONSE_HEADERS
    }

    if _is_streaming(upstream.headers):
        stream = _stream_upstream(upstream, close_client, client)
        if compat_responses_to_chat:
            stream = chat_stream_to_responses(stream)
            response_headers["content-type"] = "text/event-stream; charset=utf-8"
        return StreamingResponse(
            stream,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=response_headers.get("content-type"),
        )

    upstream_content = await upstream.aread()
    await upstream.aclose()
    if close_client:
        await client.aclose()

    upstream_payload: Any | None = None
    if _is_json_content(upstream.headers):
        try:
            upstream_payload = json.loads(upstream_content)
        except ValueError:
            upstream_payload = None

    if compat_responses_to_chat and isinstance(upstream_payload, dict):
        response_payload = chat_response_to_responses(upstream_payload)
        if settings.redaction.scan_responses:
            result = redactor.redact_payload(response_payload)
            audit.redaction(f"response:{path}", result.stats)
            response_payload = result.value
        return JSONResponse(
            response_payload,
            status_code=upstream.status_code,
            headers=response_headers,
        )

    if settings.redaction.scan_responses and upstream_payload is not None:
        try:
            result = redactor.redact_payload(upstream_payload)
        except ValueError:
            return Response(
                content=upstream_content,
                status_code=upstream.status_code,
                headers=response_headers,
                media_type=upstream.headers.get("content-type"),
            )
        audit.redaction(f"response:{path}", result.stats)
        return JSONResponse(
            result.value, status_code=upstream.status_code, headers=response_headers
        )

    return Response(
        content=upstream_content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


def _redactor_for_request(request: Request, settings: Settings) -> SecretRedactor:
    raw_rules = request.headers.get("x-redact-extra-rules")
    if not raw_rules:
        return request.app.state.redactor
    try:
        rules = [RuleConfig.model_validate(rule) for rule in json.loads(raw_rules)]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid X-Redact-Extra-Rules header") from None
    redaction = deepcopy(settings.redaction)
    redaction.rules.extend(rules)
    return SecretRedactor(redaction)


def _client_for_request(request: Request, settings: Settings) -> tuple[httpx.AsyncClient, bool]:
    client = getattr(request.app.state, "client", None)
    if client is not None:
        return client, False
    timeout = httpx.Timeout(settings.target.timeout_seconds)
    return httpx.AsyncClient(timeout=timeout), True


def _check_proxy_auth(request: Request, settings: Settings) -> None:
    api_key = settings.server.api_key
    if not api_key:
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {api_key}":
        raise HTTPException(status_code=401, detail="invalid PromptCloak API key")


def _should_bridge_responses_to_chat(request: Request, path: str, settings: Settings) -> bool:
    return (
        settings.compat.responses_to_chat
        and request.method == "POST"
        and path.rstrip("/") == "/v1/responses"
    )


def _target_url(request: Request, path: str, settings: Settings) -> str:
    base_url = request.headers.get("x-target-base-url") or settings.target.default_base_url
    base = base_url.rstrip("/")
    incoming = path if path.startswith("/") else f"/{path}"
    base_parts = urlsplit(base)
    base_path = base_parts.path.rstrip("/")
    if base_path and incoming.startswith(base_path + "/"):
        final_path = incoming
    else:
        final_path = f"{base_path}{incoming}"
    return urlunsplit((base_parts.scheme, base_parts.netloc, final_path, "", ""))


def _validate_target(target_url: str, settings: Settings) -> None:
    parsed = urlsplit(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="invalid target URL")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="target URL userinfo not allowed")
    allowed = settings.target.allowed_base_urls
    if allowed and not any(_target_matches_allowed_url(target_url, url) for url in allowed):
        raise HTTPException(status_code=403, detail="target URL not allowed")
    if settings.target.block_private_targets and _is_private_host(parsed.hostname):
        raise HTTPException(status_code=403, detail="private target URL blocked")


def _target_matches_allowed_url(target_url: str, allowed_url: str) -> bool:
    allowed = allowed_url.rstrip("/")
    return target_url == allowed or target_url.startswith(allowed + "/")


def _is_private_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
    return False


def _forward_headers(request: Request, settings: Settings) -> dict[str, str]:
    target_api_key = request.headers.get("x-target-api-key")
    target_authorization = request.headers.get("x-target-authorization")
    target_api_key_header = (
        request.headers.get("x-target-api-key-header") or settings.target.api_key_header
    ).lower()
    if target_api_key_header not in {"authorization", "x-api-key"}:
        raise HTTPException(status_code=400, detail="invalid X-Target-API-Key-Header header")
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in DROP_REQUEST_HEADERS:
            continue
        if lowered in {
            "x-target-base-url",
            "x-target-api-key",
            "x-target-api-key-header",
            "x-target-authorization",
        }:
            continue
        if lowered in CLIENT_AUTH_HEADERS:
            has_target_auth = settings.target.api_key or target_api_key or target_authorization
            if has_target_auth or not settings.target.forward_client_authorization:
                continue
        if lowered.startswith("x-redact-"):
            continue
        headers[key] = value
    if target_api_key:
        _set_target_api_key(headers, target_api_key, target_api_key_header)
    elif target_authorization:
        headers["authorization"] = target_authorization
    elif settings.target.api_key:
        _set_target_api_key(headers, settings.target.api_key, target_api_key_header)
    return headers


def _set_target_api_key(headers: dict[str, str], api_key: str, header: str) -> None:
    if header == "x-api-key":
        headers["x-api-key"] = api_key
        return
    headers["authorization"] = f"Bearer {api_key}"


def _debug_request(
    request: Request,
    path: str,
    target_url: str,
    raw_body: bytes,
    redacted_body: bytes,
    stats: RedactionStats,
    settings: Settings,
) -> None:
    if not settings.server.debug_requests:
        return
    max_chars = settings.server.debug_max_body_chars
    logger.warning(
        json.dumps(
            {
                "event": "debug_request",
                "method": request.method,
                "path": path,
                "target_url": target_url,
                "headers": _debug_headers(request),
                "redactions": stats.redactions,
                "rules": stats.rule_hits,
                "raw_body": _debug_body(raw_body, max_chars),
                "raw_body_truncated": len(raw_body.decode("utf-8", errors="replace")) > max_chars,
                "redacted_body": _debug_body(redacted_body, max_chars),
                "redacted_body_truncated": len(redacted_body.decode("utf-8", errors="replace"))
                > max_chars,
            },
            sort_keys=True,
        )
    )


def _debug_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lowered = key.lower()
        if lowered in SENSITIVE_DEBUG_HEADERS or lowered.startswith("x-redact-"):
            headers[key] = "[REDACTED_HEADER]"
        else:
            headers[key] = value
    return headers


def _debug_body(body: bytes, max_chars: int) -> str:
    text = body.decode("utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _is_json_request(request: Request) -> bool:
    return _is_json_content(request.headers)


def _is_text_request(request: Request) -> bool:
    content_type = request.headers.get("content-type", "").lower()
    return content_type.startswith("text/")


def _is_json_content(headers: httpx.Headers | Any) -> bool:
    return "application/json" in headers.get("content-type", "").lower()


def _is_streaming(headers: httpx.Headers) -> bool:
    return "text/event-stream" in headers.get("content-type", "").lower()


async def _stream_upstream(
    upstream: httpx.Response, close_client: bool, client: httpx.AsyncClient
) -> AsyncIterator[bytes]:
    try:
        async for chunk in upstream.aiter_bytes():
            yield chunk
    finally:
        await upstream.aclose()
        if close_client:
            await client.aclose()


app = create_app()


def reload_app_from_config() -> FastAPI:
    return create_app(load_settings())
