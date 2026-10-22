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
from portal.platform.inference.router.metrics import _REGISTRY


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


_AUTH = {"Authorization": "Bearer test-key"}


def _sample(metric: str, **labels: str) -> float:
    return _REGISTRY.get_sample_value(metric, labels) or 0.0


def _usage(model: str, workspace: str) -> dict[str, float]:
    """The five counters one proxied call can move, for the given labels."""
    return {
        "requests": _sample("portal_requests_by_model_total", model=model, workspace=workspace),
        "input": _sample("portal_input_tokens_total", model=model, workspace=workspace),
        "output": _sample("portal_output_tokens_total", model=model, workspace=workspace),
        "decode": _sample(
            "portal_decode_tokens_total", model=model, workspace=workspace, source="engine"
        ),
        "decode_seconds": _sample(
            "portal_decode_seconds_total", model=model, workspace=workspace, source="engine"
        ),
    }


@pytest.fixture
async def metered(monkeypatch):
    """The passthrough app with an upstream body the test supplies, for metric deltas."""
    state = SimpleNamespace(body=b"", content_type="application/json")

    async def upstream(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": state.content_type},
            stream=_Bytes(state.body),
        )

    native_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    caller = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pipeline.test"
    )
    monkeypatch.setattr(auth, "PIPELINE_API_KEY", "test-key")
    monkeypatch.setattr(load_guard, "GUARD", _Guard())
    ollama_passthrough.configure(_Registry(), native_client)
    yield state, caller
    await caller.aclose()
    await native_client.aclose()
    ollama_passthrough.configure(None, None)


async def test_non_streaming_chat_counts_one_engine_call_with_native_usage(metered):
    state, caller = metered
    model = "gemma4:metered-chat"
    workspace = ollama_passthrough.PASSTHROUGH_WORKSPACE
    state.body = json.dumps(
        {
            "model": model,
            "message": {"content": "ok"},
            "done": True,
            "prompt_eval_count": 11,
            "eval_count": 7,
            "prompt_eval_duration": 2_000_000_000,
            "eval_duration": 1_500_000_000,
        }
    ).encode()
    before = _usage(model, workspace)

    response = await caller.post(
        "/ollama/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": "hi"}], "stream": False},
        headers=_AUTH,
    )

    assert response.status_code == 200
    after = _usage(model, workspace)
    assert after["requests"] - before["requests"] == 1
    assert after["input"] - before["input"] == 11
    assert after["output"] - before["output"] == 7
    assert after["decode"] - before["decode"] == 7
    assert after["decode_seconds"] - before["decode_seconds"] == pytest.approx(1.5)


async def test_streaming_chat_reads_usage_from_the_terminal_frame_once(metered):
    state, caller = metered
    model = "gemma4:metered-stream"
    workspace = ollama_passthrough.PASSTHROUGH_WORKSPACE
    frames = [
        {"model": model, "message": {"content": "ok"}, "done": False},
        {
            "model": model,
            "message": {"content": ""},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 3,
            "eval_duration": 1_000_000_000,
        },
    ]
    state.body = ("\n".join(json.dumps(frame) for frame in frames) + "\n").encode()
    state.content_type = "application/x-ndjson"
    before = _usage(model, workspace)

    response = await caller.post(
        "/ollama/api/chat",
        json={"model": model, "messages": [], "stream": True},
        headers=_AUTH,
    )

    assert response.status_code == 200
    assert response.content == state.body  # still byte-preserving
    after = _usage(model, workspace)
    assert after["requests"] - before["requests"] == 1
    assert after["output"] - before["output"] == 3
    assert after["decode"] - before["decode"] == 3


async def test_embed_is_counted_under_its_own_workspace(metered):
    state, caller = metered
    model = "embeddinggemma:metered"
    chat = ollama_passthrough.PASSTHROUGH_WORKSPACE
    embed = ollama_passthrough.PASSTHROUGH_EMBED_WORKSPACE
    state.body = json.dumps(
        {"model": model, "embeddings": [[0.1, 0.2]], "prompt_eval_count": 9}
    ).encode()
    chat_before = _usage(model, chat)
    embed_before = _usage(model, embed)

    response = await caller.post(
        "/ollama/api/embed", json={"model": model, "input": ["a"]}, headers=_AUTH
    )

    assert response.status_code == 200
    embed_after = _usage(model, embed)
    assert embed_after["requests"] - embed_before["requests"] == 1
    assert embed_after["input"] - embed_before["input"] == 9
    assert _usage(model, chat) == chat_before


async def test_generate_without_usage_fields_is_still_counted_once(metered):
    state, caller = metered
    model = "gemma4:metered-no-usage"
    workspace = ollama_passthrough.PASSTHROUGH_WORKSPACE
    state.body = json.dumps({"model": model, "message": {"content": "ok"}, "done": True}).encode()
    before = _usage(model, workspace)

    response = await caller.post(
        "/ollama/api/generate", json={"model": model, "prompt": "hi"}, headers=_AUTH
    )

    assert response.status_code == 200
    after = _usage(model, workspace)
    assert after["requests"] - before["requests"] == 1
    assert after["output"] == before["output"]


async def test_metadata_route_is_not_counted_as_an_engine_call(metered):
    state, caller = metered
    model = "gemma4:metered-show"
    workspace = ollama_passthrough.PASSTHROUGH_WORKSPACE
    state.body = json.dumps({"model": model, "verbose": False}).encode()
    before = _usage(model, workspace)

    response = await caller.post("/ollama/api/show", json={"model": model}, headers=_AUTH)

    assert response.status_code == 200
    assert _usage(model, workspace) == before
