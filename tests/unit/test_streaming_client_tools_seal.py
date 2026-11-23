"""Streaming twin of the client-tools-only cap-seal exemption (non-streaming fix 20a75fa3f)."""

from __future__ import annotations

import json
import typing
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import portal.platform.inference.router.handlers as handlers_mod
import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.tool_repeat import (
    CITED_SYNTHESIS_REQUEST,
    ToolHopAction,
    next_tool_action,
)

# ── next_tool_action: the seal decision ──────────────────────────────


def _call(name: str, cid: str = "c1") -> dict[str, typing.Any]:
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": "{}"}}


def _hop_action(
    *,
    call_limit: int | None,
    client_tools_only: bool = False,
    owned_names: set[str] | None = None,
    calls: list[dict[str, typing.Any]] | None = None,
) -> ToolHopAction:
    owned = owned_names or set()
    hop_calls = calls if calls is not None else [_call("fetch_weather")]
    return next_tool_action(
        hop=1,
        hop_limit=20,
        bite_returns_client=False,
        synthesis_hop=False,
        calls=hop_calls,
        repeat_flags=[False] * len(hop_calls),
        dispatched=0,
        call_limit=call_limit,
        client_owned=not all(
            str((c.get("function") or {}).get("name", "")).strip() in owned for c in hop_calls
        ),
        owned_names=owned,
        client_tools_only=client_tools_only,
    )


def test_client_tools_only_hands_calls_back_on_a_capped_workspace() -> None:
    action = _hop_action(call_limit=10, owned_names=set(), client_tools_only=True)
    assert action.kind == "client"
    assert [c["function"]["name"] for c in action.calls] == ["fetch_weather"]
    assert action.dispatched == 0


def test_capped_workspace_still_seals_client_calls_without_the_flag() -> None:
    action = _hop_action(call_limit=10, owned_names=set(), client_tools_only=False)
    assert action.kind == "synthesize"
    assert action.calls == []
    assert action.cited is True


@pytest.mark.parametrize("client_tools_only", [True, False])
def test_uncapped_client_calls_hand_back_either_way(client_tools_only: bool) -> None:
    action = _hop_action(call_limit=None, client_tools_only=client_tools_only)
    assert action.kind == "client"
    assert [c["function"]["name"] for c in action.calls] == ["fetch_weather"]


def test_capped_mixed_turn_still_dispatches_only_owned_calls() -> None:
    calls = [_call("kb_search"), _call("fetch_weather", "c2")]
    action = _hop_action(call_limit=10, owned_names={"kb_search"}, calls=calls)
    assert action.kind == "dispatch"
    assert [c["function"]["name"] for c in action.calls] == ["kb_search"]
    assert action.cited is True


# ── the streaming tool loop on a capped workspace ────────────────────


class _Resp:
    def __init__(self, lines: list[str]) -> None:
        self.status_code = 200
        self._lines = lines

    async def aiter_lines(self) -> typing.AsyncIterator[str]:
        for line in self._lines:
            yield line


class _Stream:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *exc: object) -> None:
        return None


def _batch(names: list[str]) -> _Resp:
    calls = [
        {"index": i, "id": f"c{i}", "function": {"name": name, "arguments": "{}"}}
        for i, name in enumerate(names)
    ]
    chunk = {"choices": [{"delta": {"tool_calls": calls}, "finish_reason": "tool_calls"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _answer(text: str) -> _Resp:
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


async def _drive_loop(
    monkeypatch: pytest.MonkeyPatch,
    frames: list[_Resp],
    *,
    client_tools_only: bool,
) -> tuple[bytes, list[dict[str, typing.Any]], list[str]]:
    bodies: list[dict[str, typing.Any]] = []
    executed: list[str] = []

    class _Client:
        def stream(self, method: str, url: str, json: dict | None = None):  # noqa: A002
            assert json is not None
            bodies.append(dict(json))
            return _Stream(frames.pop(0))

    async def fake_dispatch(tc: dict[str, typing.Any], *_a: typing.Any, **_k: typing.Any):
        executed.append(tc["function"]["name"])
        return {"role": "tool", "tool_call_id": tc.get("id"), "content": "SNIPPET"}

    monkeypatch.setattr(st, "_http_client", _Client())
    monkeypatch.setattr(st, "_backend_type_for_url", lambda url: "ollama")
    monkeypatch.setattr(st, "_dispatch_tool_call", fake_dispatch)
    monkeypatch.setattr(st, "_configured_tool_calls", lambda _ws: 10)

    out = b""
    async for chunk in st._tool_loop_frames(
        "http://ollama.test/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": "weather in Lisbon?"}],
            "model": "m",
            "tools": [
                {"type": "function", "function": {"name": "fetch_weather", "parameters": {}}}
            ],
        },
        "auto-coding",
        "m",
        "",
        set(),
        client_tools_only=client_tools_only,
    ):
        out += chunk
    return out, bodies, executed


def _sse_payloads(raw: bytes) -> list[dict[str, typing.Any]]:
    return [
        json.loads(line[6:])
        for line in raw.splitlines()
        if line.startswith(b"data: ") and line.strip() != b"data: [DONE]"
    ]


def _sse_tool_names(raw: bytes) -> list[str]:
    return [
        str((call.get("function") or {}).get("name") or "")
        for payload in _sse_payloads(raw)
        for choice in payload.get("choices") or []
        for call in (choice.get("delta") or {}).get("tool_calls") or []
    ]


async def test_streaming_loop_hands_client_calls_back_on_a_capped_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, bodies, executed = await _drive_loop(
        monkeypatch, [_batch(["fetch_weather"])], client_tools_only=True
    )
    assert _sse_tool_names(raw) == ["fetch_weather"]
    assert executed == []
    assert len(bodies) == 1  # no cited-synthesis second turn
    assert any(
        choice.get("finish_reason") == "tool_calls"
        for payload in _sse_payloads(raw)
        for choice in payload.get("choices") or []
    )
    assert raw.count(b"data: [DONE]") == 1


async def test_streaming_loop_still_seals_client_calls_without_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, bodies, executed = await _drive_loop(
        monkeypatch,
        [_batch(["fetch_weather"]), _answer("Sealed synthesis.")],
        client_tools_only=False,
    )
    assert _sse_tool_names(raw) == []
    assert executed == []
    assert len(bodies) == 2
    assert bodies[1]["tools"] is None
    assert bodies[1]["tool_choice"] == "none"
    assert bodies[1]["messages"][-1] == CITED_SYNTHESIS_REQUEST
    assert b"Sealed synthesis." in raw


# ── propagation: selector and multi-candidate fallback ───────────────


async def test_select_stream_fn_forwards_client_tools_only_to_the_tool_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, typing.Any] = {}

    async def fake_loop(*_a: typing.Any, **kwargs: typing.Any) -> typing.AsyncIterator[bytes]:
        captured.update(kwargs)
        yield b"data: [DONE]\n\n"

    monkeypatch.setattr(st, "_stream_with_tool_loop", fake_loop)
    backend = SimpleNamespace(chat_url="http://engine/v1/chat/completions")
    gen = st._select_stream_fn(
        backend,
        {},
        MagicMock(),
        "ws",
        "m",
        "p",
        [],
        0.0,
        [],
        "",
        "",
        False,
        True,
        client_tools_only=True,
    )
    assert [c async for c in gen] == [b"data: [DONE]\n\n"]
    assert captured["client_tools_only"] is True


@pytest.mark.parametrize("kwargs,expected", [({"client_tools_only": True}, True), ({}, False)])
async def test_fallback_forwards_client_tools_only_to_the_selector(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, typing.Any],
    expected: bool,
) -> None:
    captured: dict[str, typing.Any] = {}

    async def inner(*_a: typing.Any, **_k: typing.Any) -> typing.AsyncIterator[bytes]:
        yield b"data: [DONE]\n\n"

    def fake_select(*_a: typing.Any, **kw: typing.Any) -> typing.AsyncIterator[bytes]:
        captured.update(kw)
        return inner()

    monkeypatch.setattr(st, "_select_stream_fn", fake_select)
    backend = SimpleNamespace(id="b0", type="ollama", chat_url="http://engine/v1/chat/completions")
    gen = st._stream_with_fallback(
        backend,
        {},
        "ws",
        "m",
        "p",
        [],
        0.0,
        True,
        [],
        False,
        "",
        "",
        [],
        MagicMock(),
        {},
        **kwargs,
    )
    assert [c async for c in gen] == [b"data: [DONE]\n\n"]
    assert captured["client_tools_only"] is expected


# ── handler end-to-end: real builder, selector and tool loop ─────────


@pytest.fixture
def api() -> typing.Iterator[typing.Any]:
    from fastapi.testclient import TestClient

    from portal.platform.inference.router_pipe import app
    from tests.unit.test_pipeline import _make_fake_backend

    handlers_mod.registry = _make_fake_backend()
    with TestClient(app) as test_client:
        yield test_client
    handlers_mod.registry = None


def _seal_backend() -> typing.Any:
    return SimpleNamespace(
        id="fake-ollama",
        type="ollama",
        chat_url="http://engine/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h: h if h == "m" else None,
    )


def _client_tool_schema() -> dict[str, typing.Any]:
    return {"type": "function", "function": {"name": "fetch_weather", "parameters": {}}}


def _route(
    monkeypatch: pytest.MonkeyPatch,
    ws: str,
    body: dict[str, typing.Any],
    backend: typing.Any,
) -> None:
    async def resolved_route(_request: typing.Any, _slot: typing.Any):
        return ws, body, True, "", [backend]

    monkeypatch.setattr(handlers_mod, "_resolve_request_route", resolved_route)
    monkeypatch.setattr(
        handlers_mod,
        "_select_streaming_backend",
        lambda _workspace, _candidates: (backend, "m", None, None, None, None),
    )


async def test_handler_streams_client_calls_back_on_a_capped_workspace(
    api: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.platform.inference.router.auth import PIPELINE_API_KEY

    ws = "test-stream-seal-ws"
    monkeypatch.setitem(st.WORKSPACES, ws, {"model_hint": "m", "max_tool_calls": 10})
    monkeypatch.setattr(st, "_model_supports_tools", lambda _m: True)
    backend = _seal_backend()
    body = {
        "model": ws,
        "stream": True,
        "messages": [{"role": "user", "content": "weather in Lisbon?"}],
        "tools": [_client_tool_schema()],
        "portal_client_tools_only": True,
    }
    _route(monkeypatch, ws, body, backend)
    seen: list[dict[str, typing.Any]] = []

    class _Client:
        def stream(self, _method: str, _url: str, *, json: dict):  # noqa: A002
            seen.append(dict(json))
            return _Stream(_batch(["fetch_weather"]))

    monkeypatch.setattr(st, "_http_client", _Client())
    response = api.post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
    )
    assert response.status_code == 200, response.text
    assert len(seen) == 1  # no cited-synthesis second turn
    assert "portal_client_tools_only" not in seen[0]  # never leaked to the engine
    assert [t["function"]["name"] for t in seen[0]["tools"]] == ["fetch_weather"]
    assert _sse_tool_names(response.content) == ["fetch_weather"]
    assert response.text.count("[DONE]") == 1


async def test_handler_capped_workspace_still_seals_without_the_flag(
    api: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portal.platform.inference import tool_registry as registry_mod
    from portal.platform.inference.router.auth import PIPELINE_API_KEY

    ws = "test-stream-seal-ws"
    monkeypatch.setitem(
        st.WORKSPACES, ws, {"model_hint": "m", "max_tool_calls": 10, "tools": ["kb_search"]}
    )
    monkeypatch.setattr(st, "_model_supports_tools", lambda _m: True)

    async def refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", refresh)
    monkeypatch.setattr(registry_mod.tool_registry, "list_tool_names", lambda: ["kb_search"])
    monkeypatch.setattr(
        registry_mod.tool_registry,
        "get_openai_tools",
        lambda names: [
            {"type": "function", "function": {"name": n, "parameters": {}}} for n in names
        ],
    )
    backend = _seal_backend()
    body = {
        "model": ws,
        "stream": True,
        "messages": [{"role": "user", "content": "weather in Lisbon?"}],
        "tools": [_client_tool_schema()],
    }
    _route(monkeypatch, ws, body, backend)
    seen: list[dict[str, typing.Any]] = []
    frames = [_batch(["fetch_weather"]), _answer("Sealed synthesis.")]

    class _Client:
        def stream(self, _method: str, _url: str, *, json: dict):  # noqa: A002
            seen.append(dict(json))
            return _Stream(frames.pop(0))

    monkeypatch.setattr(st, "_http_client", _Client())
    response = api.post(
        "/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {PIPELINE_API_KEY}"},
    )
    assert response.status_code == 200, response.text
    assert len(seen) == 2
    assert seen[1]["tools"] is None
    assert seen[1]["tool_choice"] == "none"
    assert seen[1]["messages"][-1] == CITED_SYNTHESIS_REQUEST
    assert _sse_tool_names(response.content) == []
    assert "Sealed synthesis." in response.text
