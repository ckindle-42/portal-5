"""Native Ollama passthrough preserves bytes while enforcing pipeline auth/guard."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference import load_guard
from portal.platform.inference.load_guard import LoadRefusedError
from portal.platform.inference.router import auth, ollama_passthrough
from portal.platform.inference.router.app import app


class _Registry:
    def list_healthy_backends(self):
        return [SimpleNamespace(type="ollama", url="http://ollama.test:11434")]


class _Bytes(httpx.AsyncByteStream):
    def __init__(self, value: bytes):
        self.value = value

    async def __aiter__(self):
        yield self.value


class _Guard:
    def __init__(self, *, refuse: bool = False):
        self.refuse = refuse
        self.admitted: list[tuple[str, str]] = []
        self.begun: list[tuple[str, str]] = []
        self.released = 0
        self.ended = 0

    async def admit(self, base: str, model: str):
        self.admitted.append((base, model))
        if self.refuse:
            raise LoadRefusedError("would exceed host memory")

        def release():
            self.released += 1

        return release

    def begin(self, engine: str, model: str):
        self.begun.append((engine, model))

        def end():
            self.ended += 1

        return end


@pytest.fixture
async def passthrough(monkeypatch):
    calls: list[httpx.Request] = []

    async def upstream(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        payload = json.loads(request.content or b"{}")
        if payload.get("stream"):
            body = b'{"message":{"content":"ok","thinking":"trace"},"done":true}\n'
            content_type = "application/x-ndjson"
        else:
            body = b'{"message":{"content":"ok","thinking":"trace"},"done":true}'
            content_type = "application/json"
        return httpx.Response(
            200,
            headers={"content-type": content_type},
            stream=_Bytes(body),
        )

    native_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    caller = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pipeline.test"
    )
    guard = _Guard()
    monkeypatch.setattr(auth, "PIPELINE_API_KEY", "test-key")
    monkeypatch.setattr(load_guard, "GUARD", guard)
    ollama_passthrough.configure(_Registry(), native_client)
    yield caller, calls, guard
    await caller.aclose()
    await native_client.aclose()
    ollama_passthrough.configure(None, None)


@pytest.mark.parametrize("stream", [True, False])
async def test_chat_preserves_request_response_bytes_and_thinking(passthrough, stream):
    caller, calls, guard = passthrough
    body = (
        b'{"model":"gemma4:test","messages":[{"role":"user","content":"hi"}],'
        b'"think":"low","stream":' + (b"true" if stream else b"false") + b"}"
    )

    response = await caller.post(
        "/ollama/api/chat",
        content=body,
        headers={"Authorization": "Bearer test-key", "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert calls[0].url.path == "/api/chat"
    assert calls[0].content == body
    expected = b'{"message":{"content":"ok","thinking":"trace"},"done":true}'
    if stream:
        expected += b"\n"
    assert response.content == expected
    assert b'"thinking":"trace"' in response.content
    assert "authorization" not in calls[0].headers
    assert guard.admitted == [("http://ollama.test:11434", "gemma4:test")]
    assert guard.begun == [("ollama", "gemma4:test")]
    assert guard.released == guard.ended == 1


async def test_missing_auth_is_rejected_before_upstream(passthrough):
    caller, calls, _guard = passthrough

    response = await caller.post(
        "/ollama/api/generate", json={"model": "gemma4:test", "prompt": "hi"}
    )

    assert response.status_code == 401
    assert calls == []


async def test_guard_refusal_is_ollama_error_shape(passthrough, monkeypatch):
    caller, calls, _guard = passthrough
    refusing = _Guard(refuse=True)
    monkeypatch.setattr(load_guard, "GUARD", refusing)

    response = await caller.post(
        "/ollama/api/generate",
        json={"model": "large:test", "prompt": "hi"},
        headers={"Authorization": "Bearer test-key"},
    )

    assert response.status_code == 507
    assert response.json() == {"error": "would exceed host memory"}
    assert calls == []


async def test_read_only_routes_proxy_auth_and_show_body(passthrough):
    caller, calls, guard = passthrough

    ps = await caller.get("/ollama/api/ps", headers={"Authorization": "Bearer test-key"})
    tags = await caller.get("/ollama/api/tags", headers={"Authorization": "Bearer test-key"})
    show_body = b'{"model":"gemma4:test","verbose":true}'
    show = await caller.post(
        "/ollama/api/show",
        content=show_body,
        headers={"Authorization": "Bearer test-key", "Content-Type": "application/json"},
    )

    assert [call.url.path for call in calls] == ["/api/ps", "/api/tags", "/api/show"]
    assert calls[2].content == show_body
    assert all(response.status_code == 200 for response in (ps, tags, show))
    assert guard.admitted == guard.begun == []


async def test_client_disconnect_while_waiting_for_upstream_cancels_and_releases(monkeypatch):
    """A non-streaming Ollama call sends headers only when generation ends; a
    client that leaves before then must cancel it and release the guard (W3)."""
    import asyncio

    from starlette.requests import Request

    from portal.platform.inference.router import disconnect

    monkeypatch.setattr(disconnect, "POLL_S", 0.02)
    monkeypatch.setattr(auth, "_verify_key", lambda authorization: None)
    upstream_cancelled = asyncio.Event()

    async def upstream(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.sleep(30)  # generating; no headers yet
        except asyncio.CancelledError:
            upstream_cancelled.set()
            raise
        return httpx.Response(200)  # pragma: no cover

    guard = _Guard()
    monkeypatch.setattr(load_guard, "GUARD", guard)
    monkeypatch.setattr(ollama_passthrough, "_verify_key", lambda authorization: None)
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    ollama_passthrough.configure(_Registry(), client)
    body = json.dumps({"model": "m", "stream": False}).encode()
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/ollama/api/chat",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }
    try:
        response = await ollama_passthrough.chat(Request(scope, receive), authorization="x")
    finally:
        ollama_passthrough.configure(None, None)
        await client.aclose()

    assert response.status_code == disconnect.CLIENT_CLOSED
    assert upstream_cancelled.is_set()
    assert guard.released == 1
    assert guard.ended == 1
