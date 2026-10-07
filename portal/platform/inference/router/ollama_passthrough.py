"""Authenticated, byte-preserving native Ollama routes for MCP clients.

These routes are the only supported HTTP path for callers that need Ollama's
native request and response fields (including ``think`` and
``message.thinking``). The dedicated client deliberately has no
``OllamaNativeTransport`` installed: that transport translates the OpenAI
``/v1`` surface and would change native bytes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

import portal.platform.inference.load_guard as load_guard
from portal.platform.inference.load_guard import OLLAMA, LoadRefusedError, set_load_wait
from portal.platform.inference.router.auth import _verify_key

logger = logging.getLogger(__name__)

_registry: Any = None
_client: httpx.AsyncClient | None = None

_REQUEST_HEADERS = {"accept", "accept-encoding", "content-type", "user-agent"}
_RESPONSE_HEADERS = {
    "cache-control",
    "content-encoding",
    "content-length",
    "content-type",
    "etag",
    "last-modified",
    "retry-after",
}


def configure(registry: Any, client: httpx.AsyncClient | None) -> None:
    """Install the live backend registry and plain native client at startup."""
    global _registry, _client
    _registry = registry
    _client = client


def _backend() -> Any:
    if _registry is None:
        raise HTTPException(status_code=503, detail="Backend registry not initialised")
    backend = next(
        (item for item in _registry.list_healthy_backends() if item.type == OLLAMA), None
    )
    if backend is None:
        raise HTTPException(status_code=503, detail="No healthy Ollama backend")
    return backend


def _model(body: bytes) -> str:
    try:
        decoded = json.loads(body) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    value = decoded.get("model", "") if isinstance(decoded, dict) else ""
    return value if isinstance(value, str) else str(value or "")


def _close_callbacks(*callbacks: Callable[[], None] | None) -> None:
    for callback in callbacks:
        if callback is not None:
            try:
                callback()
            except Exception:
                logger.exception("native Ollama request cleanup failed")


async def _proxy(
    request: Request,
    authorization: str | None,
    native_path: str,
    *,
    inference: bool,
) -> StreamingResponse | JSONResponse:
    _verify_key(authorization)
    if _client is None:
        raise HTTPException(status_code=503, detail="Native Ollama client not initialised")
    backend = _backend()
    base = backend.url.rstrip("/")
    target = f"{base}/api/{native_path}"
    query = request.url.query
    if query:
        target = f"{target}?{query}"

    body = await request.body() if request.method != "GET" else b""
    headers = {
        key: value for key, value in request.headers.items() if key.lower() in _REQUEST_HEADERS
    }
    request_args: dict[str, Any] = {"method": request.method, "url": target, "headers": headers}
    if request.method != "GET":
        request_args["content"] = body

    release: Callable[[], None] | None = None
    end: Callable[[], None] | None = None
    if inference:
        guard = load_guard.GUARD
        if guard is None:
            raise HTTPException(status_code=503, detail="Host memory guard not initialised")
        set_load_wait(request.headers.get("x-portal-load-wait"))
        model = _model(body)
        if model:
            try:
                release = await guard.admit(base, model)
            except LoadRefusedError as exc:
                return JSONResponse(status_code=507, content={"error": str(exc)})
            end = guard.begin(OLLAMA, model)

    try:
        upstream_request = _client.build_request(**request_args)
        upstream = await _client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        _close_callbacks(release, end)
        return JSONResponse(
            status_code=502,
            content={"error": f"native Ollama request failed: {exc}"},
        )

    response_headers = {
        key: value for key, value in upstream.headers.items() if key.lower() in _RESPONSE_HEADERS
    }

    async def _body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            _close_callbacks(release, end)

    return StreamingResponse(_body(), status_code=upstream.status_code, headers=response_headers)


async def chat(request: Request, authorization: str | None = Header(default=None)) -> Any:
    return await _proxy(request, authorization, "chat", inference=True)


async def generate(request: Request, authorization: str | None = Header(default=None)) -> Any:
    return await _proxy(request, authorization, "generate", inference=True)


async def embed(request: Request, authorization: str | None = Header(default=None)) -> Any:
    return await _proxy(request, authorization, "embed", inference=True)


async def ps(request: Request, authorization: str | None = Header(default=None)) -> Any:
    return await _proxy(request, authorization, "ps", inference=False)


async def tags(request: Request, authorization: str | None = Header(default=None)) -> Any:
    return await _proxy(request, authorization, "tags", inference=False)


async def show(request: Request, authorization: str | None = Header(default=None)) -> Any:
    return await _proxy(request, authorization, "show", inference=False)
