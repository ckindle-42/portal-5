"""P-1: an empty streamed tool-loop hop gets one non-streamed retry that salvages a
malformed tool call. P-2: the model a request failed over from is not evicted."""

from __future__ import annotations

import asyncio

from portal.platform.inference import load_guard as lg
from portal.platform.inference.router import streaming

TOOLS = [
    {"type": "function", "function": {"name": "compliance_read", "parameters": {"type": "object"}}}
]


def test_protection_orders_eviction_but_never_causes_a_refusal():
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "")
    resident = {"a": 10, "b": 20}
    assert g._ollama_idle(resident) == 30.0
    g.protect(lg.OLLAMA, "b")
    assert g._ollama_idle(resident) == 10.0  # protected goes last
    assert g._ollama_idle(resident, include_protected=True) == 30.0  # but yields before refusal
    assert "b" in g.protected(lg.OLLAMA) and "b" not in g.protected(lg.OMLX)
    g.protect(lg.OLLAMA, "b", seconds=-1)  # expired
    assert g._ollama_idle(resident) == 30.0


def test_protect_failover_uses_the_running_guard(monkeypatch):
    monkeypatch.setattr(lg, "GUARD", None)
    lg.protect_failover(lg.OMLX, "m")  # no guard: a no-op, never an error
    g = lg.LoadGuard(omlx_url=lambda: None)
    monkeypatch.setattr(lg, "GUARD", g)
    lg.protect_failover(lg.OMLX, "Qwen3.8-27B-oQ4e-mtp")
    lg.protect_failover("vllm", "x")  # engines load_guard does not manage are ignored
    assert g.protected(lg.OMLX) == {"Qwen3.8-27B-oQ4e-mtp"}


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p


class _Client:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.sent = resp, exc, None

    async def post(self, url, json):
        self.sent = json
        if self.exc:
            raise self.exc
        return self.resp


def _msg(content="", tool_calls=None, reasoning=None):
    message = {"content": content, "tool_calls": tool_calls}
    if reasoning is not None:
        message["reasoning"] = reasoning
    return {"choices": [{"message": message}]}


def _rescue(monkeypatch, client):
    monkeypatch.setattr(streaming, "_http_client", client)
    return asyncio.run(
        streaming._rescue_empty_hop(
            "http://omlx/v1/chat/completions", {"tools": TOOLS, "stream": True}
        )
    )


def test_a_malformed_tool_call_is_salvaged_from_the_non_streamed_reply(monkeypatch):
    raw = '<tool_call>{"name": "compliance_read", "arguments": {"ref": "OT-POL-007"}}}</tool_call>'
    client = _Client(_Resp(200, _msg(raw)))
    text, calls, reasoning = _rescue(monkeypatch, client)
    assert client.sent["stream"] is False
    assert [c["function"]["name"] for c in calls] == ["compliance_read"] and text == ""
    assert reasoning == ""


def test_proper_tool_calls_and_plain_answers_come_back_as_they_are(monkeypatch):
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "compliance_read", "arguments": "{}"},
    }
    assert _rescue(monkeypatch, _Client(_Resp(200, _msg("", [call], "rescue thought")))) == (
        "",
        [call],
        "rescue thought",
    )
    assert _rescue(monkeypatch, _Client(_Resp(200, _msg("<think>x</think>The answer.")))) == (
        "The answer.",
        [],
        "x",
    )


def test_a_failed_rescue_falls_back_to_the_no_answer_path(monkeypatch):
    assert _rescue(monkeypatch, _Client(exc=OSError("down"))) == ("", [], "")
    assert _rescue(monkeypatch, _Client(_Resp(500, {}))) == ("", [], "")


# ── a local context refusal must not pin the backend (P-2 exemption) ──


def _overflow_envelope() -> bytes:
    import json

    message = (
        "⚠️ **The conversation exceeds this workspace's context** "
        "(about 44,278 tokens for a 32,768-token window), so it was not sent. "
        "Start a new chat, or send less material in one turn."
    )
    return f"data: {json.dumps({'error': message})}\n\n".encode()


def _status_envelope(status: int, message: str) -> bytes:
    import json

    return f"data: {json.dumps({'error': message, 'status': status})}\n\n".encode()


def _fb_backend(bid: str) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        id=bid,
        type="ollama",
        chat_url=f"http://{bid}/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h, _m=["m"]: h if h in _m else None,
    )


async def _run_fallback(monkeypatch, inner_chunks, pinned, fallback_calls, ns_result=None):
    from unittest.mock import MagicMock

    async def inner(*_a, **_k):
        for c in inner_chunks:
            yield c

    async def fake_ns(backend, *_a, **_kw):
        fallback_calls.append(backend.id)
        return ns_result

    monkeypatch.setattr(
        streaming, "protect_failover", lambda engine, model: pinned.append((engine, model))
    )
    monkeypatch.setattr(streaming, "_select_stream_fn", lambda *a, **k: inner())
    monkeypatch.setattr(streaming, "_try_non_streaming", fake_ns)
    gen = streaming._stream_with_fallback(
        _fb_backend("b0"),
        {},
        "ws",
        "m",
        "p",
        [],
        0.0,
        False,
        [],
        False,
        "",
        "",
        [_fb_backend("b1")],
        MagicMock(),
        {},
    )
    out = []
    async for chunk in gen:
        out.append(chunk)
    return out


def test_a_local_context_refusal_never_pins_and_still_cascades(monkeypatch):
    pinned: list[tuple[str, str]] = []
    fallback_calls: list[str] = []

    async def run():
        return await _run_fallback(
            monkeypatch, [_overflow_envelope(), b"data: [DONE]\n\n"], pinned, fallback_calls
        )

    out = asyncio.run(run())
    assert pinned == []  # nothing was sent to any backend: no model failed
    assert fallback_calls == ["b1"]  # a bigger-window candidate is still tried
    assert any(b"exceeds this workspace's context" in c for c in out)  # the refusal surfaces


def test_a_real_backend_failure_still_pins(monkeypatch):
    pinned: list[tuple[str, str]] = []
    fallback_calls: list[str] = []

    async def run():
        return await _run_fallback(
            monkeypatch,
            [_status_envelope(503, "Backend returned HTTP 503: unavailable"), b"data: [DONE]\n\n"],
            pinned,
            fallback_calls,
        )

    asyncio.run(run())
    assert pinned == [("ollama", "m")]


def test_non_streaming_local_refusal_returns_none_without_a_pin(monkeypatch):
    from portal.platform.inference.router import non_streaming as ns
    from portal.platform.inference.router.context_budget import ContextOverflowError

    guard = lg.LoadGuard(omlx_url=lambda: None)
    monkeypatch.setattr(lg, "GUARD", guard)

    def refuse(_body, **_kw):
        raise ContextOverflowError("ws", "m", 44278, 32768)

    monkeypatch.setattr(ns, "fit_context", refuse)
    monkeypatch.setattr(ns, "_http_client", object())  # past the "not ready" bail-out
    result = asyncio.run(ns._try_non_streaming(_fb_backend("b0"), {"messages": []}, "ws", 0.0))
    assert result is None
    # the refusal was local: the backend never failed, so nothing is pinned
    assert guard.protected(lg.OLLAMA) == set() and guard.protected(lg.OMLX) == set()
