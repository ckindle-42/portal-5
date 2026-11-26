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
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

import portal.platform.inference.load_guard as load_guard
from portal.platform.inference.load_guard import OLLAMA, LoadRefusedError, set_load_wait
from portal.platform.inference.router import safety_guard
from portal.platform.inference.router.auth import _verify_key
from portal.platform.inference.router.disconnect import cancel_on_disconnect
from portal.platform.inference.router.power import _record_engine_call

logger = logging.getLogger(__name__)

_registry: Any = None
_client: httpx.AsyncClient | None = None
_model_config_registry: Any = None
_uncensored_models: set[str] = set()

#: Synthetic workspaces for native calls, which carry no workspace id of their own.
PASSTHROUGH_WORKSPACE = "native-passthrough"
PASSTHROUGH_EMBED_WORKSPACE = "native-embed"

#: Body bytes kept to read the engine's usage block: a whole non-streaming
#: answer, or a stream's terminal frame. Larger bodies still count as calls.
_USAGE_TAIL_BYTES = 256 * 1024

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


def _configured_uncensored_models() -> set[str]:
    global _model_config_registry, _uncensored_models
    if _registry is _model_config_registry:
        return _uncensored_models
    from portal.platform.inference.config import load_portal_config

    config = load_portal_config()
    hints: set[str] = set()
    for workspace_id, workspace in config.workspaces.items():
        base_marked = (
            workspace.guardrail == "uncensored"
            or "uncensored" in workspace_id.casefold()
            or "abliterated" in workspace_id.casefold()
        )
        if base_marked and workspace.model_hint:
            hints.add(workspace.model_hint)
        for variant, values in workspace.variants.items():
            hint = values.get("model_hint") or workspace.model_hint
            marked = (
                base_marked
                or values.get("guardrail") == "uncensored"
                or "uncensored" in variant.casefold()
                or "abliterated" in variant.casefold()
                or bool(
                    hint
                    and any(marker in hint.casefold() for marker in ("uncensored", "abliterated"))
                )
            )
            if marked and hint:
                hints.add(hint)
    backends = getattr(_registry, "_backends", {})
    if not isinstance(backends, dict):
        return set()
    markers = ("uncensored", "abliterated")
    models = set(hints)
    for backend in backends.values():
        if getattr(backend, "type", "") != OLLAMA:
            continue
        models.update(
            str(tag)
            for tag in getattr(backend, "models", ())
            if str(tag) in hints or any(marker in str(tag).casefold() for marker in markers)
        )
        aliases = getattr(backend, "aliases", {})
        if not isinstance(aliases, dict):
            continue
        for alias, target in aliases.items():
            if (
                alias in hints
                or target in hints
                or any(
                    marker in str(tag).casefold() for marker in markers for tag in (alias, target)
                )
            ):
                models.update((str(alias), str(target)))
    _model_config_registry = _registry
    _uncensored_models = models
    return models


def _native_refusal(native_path: str, model: str, hit: safety_guard.GuardHit) -> JSONResponse:
    payload: dict[str, Any] = {
        "model": model,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "done": True,
        "done_reason": "stop",
    }
    if native_path == "chat":
        payload["message"] = {"role": "assistant", "content": hit.text}
    else:
        payload["response"] = hit.text
    return JSONResponse(content=payload, headers={"x-portal-safety-guard": hit.kind})


def _close_callbacks(*callbacks: Callable[[], None] | None) -> None:
    for callback in callbacks:
        if callback is not None:
            try:
                callback()
            except Exception:
                logger.exception("native Ollama request cleanup failed")


def _workspace(native_path: str) -> str:
    """Workspace label for a proxied call; embeddings get their own so they can be split."""
    return PASSTHROUGH_EMBED_WORKSPACE if native_path == "embed" else PASSTHROUGH_WORKSPACE


def _body_usage(tail: bytes) -> dict[str, Any]:
    """The engine's usage block: the whole JSON body, else the last NDJSON frame."""
    text = tail.decode("utf-8", "replace").strip()
    for candidate in (text, text.rsplit("\n", 1)[-1]):
        try:
            body = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(body, dict):
            return body
    return {}


def _relay(
    upstream: httpx.Response,
    *,
    workspace: str | None,
    model: str,
    on_close: Callable[[], None],
) -> AsyncIterator[bytes]:
    """Relay upstream bytes unchanged, then release the guard and count the call once."""

    async def chunks() -> AsyncIterator[bytes]:
        tail = bytearray()
        try:
            async for chunk in upstream.aiter_raw():
                tail = (tail + chunk)[-_USAGE_TAIL_BYTES:]
                yield chunk
        finally:
            await upstream.aclose()
            on_close()
            if workspace is not None and upstream.status_code == 200:
                _record_engine_call(model, workspace, _body_usage(bytes(tail)))

    return chunks()


async def _proxy(
    request: Request,
    authorization: str | None,
    native_path: str,
    *,
    inference: bool,
) -> Response:
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
    model = _model(body)
    if (
        inference
        and native_path in {"chat", "generate"}
        and model.casefold() in {tag.casefold() for tag in _configured_uncensored_models()}
    ):
        try:
            decoded_body = json.loads(body) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded_body = {}
        hit = safety_guard.check_body(decoded_body)
        if hit is not None:
            return _native_refusal(native_path, model, hit)
    headers = {
        key: value for key, value in request.headers.items() if key.lower() in _REQUEST_HEADERS
    }
    request_args: dict[str, Any] = {"method": request.method, "url": target, "headers": headers}
    if request.method != "GET":
        request_args["content"] = body

    release: Callable[[], None] | None = None
    end: Callable[[], None] | None = None

    async def _open() -> httpx.Response | JSONResponse:
        """Admit, then wait for upstream headers. A non-streaming Ollama call
        sends its headers only when generation ends, so this phase must be
        disconnect-aware or abandoned work runs to completion (W3)."""
        nonlocal release, end
        if inference:
            guard = load_guard.GUARD
            if guard is None:
                raise HTTPException(status_code=503, detail="Host memory guard not initialised")
            set_load_wait(request.headers.get("x-portal-load-wait"))
            if model:
                try:
                    release, end = await guard.admit_and_begin_ollama(base, model)
                except LoadRefusedError as exc:
                    return JSONResponse(status_code=507, content={"error": str(exc)})
        try:
            upstream_request = _client.build_request(**request_args)
            return await _client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            _close_callbacks(release, end)
            return JSONResponse(
                status_code=502,
                content={"error": f"native Ollama request failed: {exc}"},
            )
        except BaseException:
            _close_callbacks(release, end)
            raise

    opened: httpx.Response | Response = await cancel_on_disconnect(
        request, _open(), "ollama_passthrough"
    )
    if not isinstance(opened, httpx.Response):
        return opened  # 507/502/499: _open already released what it took
    upstream = opened

    response_headers = {
        key: value for key, value in upstream.headers.items() if key.lower() in _RESPONSE_HEADERS
    }

    return StreamingResponse(
        _relay(
            upstream,
            workspace=_workspace(native_path) if inference else None,
            model=model,
            on_close=lambda: _close_callbacks(release, end),
        ),
        status_code=upstream.status_code,
        headers=response_headers,
    )


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
