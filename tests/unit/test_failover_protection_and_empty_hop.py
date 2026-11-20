"""P-1: an empty streamed tool-loop hop gets one non-streamed retry that salvages a
malformed tool call. P-2: the seat that SERVED a failover is protected, and the model
that failed is the first eviction candidate (live 2026-11-20)."""

from __future__ import annotations

import asyncio
import json

from portal.platform.inference import load_guard as lg
from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming

TOOLS = [
    {"type": "function", "function": {"name": "compliance_read", "parameters": {"type": "object"}}}
]

#: The two models the 2026-11-20 live sequence names: the GGUF that answered nothing
#: (with tools on and off) and the oMLX seat it then blocked.
NEMOTRON = "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"
QWEN_OMLX = "Qwen3.8-27B-oQ4e-mtp"


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


async def _run_fallback(monkeypatch, inner_chunks, pinned, fallback_calls, ns_result="missing"):
    from unittest.mock import MagicMock

    failed: list[tuple[str, str]] = []

    async def inner(*_a, **_k):
        for c in inner_chunks:
            yield c

    async def fake_ns(backend, *_a, **_kw):
        fallback_calls.append(backend.id)
        return None if ns_result == "missing" else ns_result

    monkeypatch.setattr(
        streaming, "protect_failover", lambda engine, model: pinned.append((engine, model))
    )
    monkeypatch.setattr(
        streaming, "note_failure", lambda engine, model: failed.append((engine, model))
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
    return out, failed


def test_a_local_context_refusal_never_pins_and_still_cascades(monkeypatch):
    pinned: list[tuple[str, str]] = []
    fallback_calls: list[str] = []

    async def run():
        return await _run_fallback(
            monkeypatch, [_overflow_envelope(), b"data: [DONE]\n\n"], pinned, fallback_calls
        )

    out, failed = asyncio.run(run())
    assert pinned == []  # nothing was sent to any backend: no model failed
    assert failed == []  # nor is a local refusal a backend failure
    assert fallback_calls == ["b1"]  # a bigger-window candidate is still tried
    assert any(b"exceeds this workspace's context" in c for c in out)  # the refusal surfaces


def test_a_failed_stream_marks_the_failed_model_first_for_eviction(monkeypatch):
    """Live 2026-11-20: the failed source was protected for 300 s and blocked a healthy seat."""
    pinned: list[tuple[str, str]] = []
    fallback_calls: list[str] = []

    async def run():
        return await _run_fallback(
            monkeypatch,
            [_status_envelope(503, "Backend returned HTTP 503: unavailable"), b"data: [DONE]\n\n"],
            pinned,
            fallback_calls,
        )

    _out, failed = asyncio.run(run())
    assert failed == [("ollama", "m")]  # the model that failed, evicted first
    assert pinned == []  # a failure is never a protected seat


def test_the_fallback_candidate_that_served_is_the_protected_seat(monkeypatch):
    from unittest.mock import MagicMock

    served = MagicMock()
    served.headers = {"x-portal-route": "ws;b1;served-model"}
    served.body = b'{"choices": [{"message": {"content": "hi"}}]}'
    pinned: list[tuple[str, str]] = []
    fallback_calls: list[str] = []

    async def run():
        return await _run_fallback(
            monkeypatch,
            [_status_envelope(503, "Backend returned HTTP 503: unavailable"), b"data: [DONE]\n\n"],
            pinned,
            fallback_calls,
            ns_result=served,
        )

    asyncio.run(run())
    assert pinned == [("ollama", "served-model")]


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


# ── the live 2026-11-20 non-streaming sequence ──────────────────────────────


class _BackendResp:
    def __init__(self, status: int, payload: dict) -> None:
        self.status_code = status
        self._payload = payload
        self.content = json.dumps(payload).encode()

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://backend/v1/chat/completions"),
                response=httpx.Response(self.status_code, content=self.content),
            )


class _Backend:
    def __init__(self, *responses: dict) -> None:
        self.responses = list(responses)
        self.sent: list[dict] = []

    async def post(self, url, json=None, timeout=None):  # noqa: A002 - httpx's kwarg name
        self.sent.append(json)
        return _BackendResp(200, self.responses.pop(0))


def _ns_backend(bid: str, engine: str, model: str, *, serves: str | None = None):
    """A backend that serves ``model`` and, when ``serves`` is given, that hint's copy too."""
    from types import SimpleNamespace

    hints = {model, serves} - {None}
    return SimpleNamespace(
        id=bid,
        type=engine,
        chat_url=f"http://{bid}/v1/chat/completions",
        models=[model],
        url=f"http://{bid}",
        resolve_model=lambda hint: model if hint in hints else None,
    )


def _emptied_by_reasoning() -> dict:
    """What Nemotron returned at max_tokens=16: no content, all budget in reasoning."""
    return {
        "model": NEMOTRON,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "", "reasoning": "Let me think..."},
                "finish_reason": "length",
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 16, "total_tokens": 136},
    }


def _served() -> dict:
    return {
        "model": QWEN_OMLX,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "the answer"},
                "finish_reason": "stop",
            }
        ],
    }


def _ns_run(monkeypatch, responses: dict[str, list[dict]], workspace_id: str = "auto-daily"):
    """Drive _try_non_streaming over the live sequence's candidates, one shared `tried`."""
    guard = lg.LoadGuard(omlx_url=lambda: None)
    monkeypatch.setattr(lg, "GUARD", guard)
    monkeypatch.setattr(ns, "fit_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(ns, "WORKSPACES", {workspace_id: {"model_hint": NEMOTRON}})
    clients = {}
    for bid, payloads in responses.items():
        clients[bid] = _Backend(*payloads)
    return guard, clients


def test_the_failed_hop_is_never_protected_and_the_served_seat_is(monkeypatch):
    """Property 1: protection names the backend that SERVED, never the one that failed."""
    guard, clients = _ns_run(
        monkeypatch, {"ollama-general": [_emptied_by_reasoning()], "omlx-coding": [_served()]}
    )
    body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 16}
    tried: dict[tuple[str, str], str] = {}

    async def run():
        first = await ns._try_non_streaming(
            _ns_backend("ollama-general", "ollama", NEMOTRON), body, "auto-daily", 0.0, tried=tried
        )
        monkeypatch.setattr(ns, "_http_client", clients["omlx-coding"])
        second = await ns._try_non_streaming(
            _ns_backend("omlx-coding", "omlx", QWEN_OMLX, serves=NEMOTRON),
            body,
            "auto-daily",
            0.0,
            tried=tried,
        )
        return first, second

    monkeypatch.setattr(ns, "_http_client", clients["ollama-general"])
    first, second = asyncio.run(run())

    assert first is None and second is not None
    # the hop that answered nothing is the first eviction candidate...
    assert lg.model_key(NEMOTRON) in guard.failed(lg.OLLAMA)
    # ...and nothing pinned it for 300 s (the live "failover protected" shield)
    assert guard.failover_protected(lg.OLLAMA) == set()
    # the seat that served the failover is the protected one
    assert guard.failover_protected(lg.OMLX) == {QWEN_OMLX}
    assert clients["ollama-general"].sent[0]["max_tokens"] == 16


def test_a_spent_reasoning_budget_is_reported_as_that_cause(monkeypatch):
    """Property 3: finish_reason=length with the budget all in reasoning is not
    "the model returned nothing" — the reason names the budget."""
    guard, clients = _ns_run(monkeypatch, {"ollama-general": [_emptied_by_reasoning()]})
    body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 16}
    tried: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(ns, "_http_client", clients["ollama-general"])
    result = asyncio.run(
        ns._try_non_streaming(
            _ns_backend("ollama-general", "ollama", NEMOTRON), body, "auto-daily", 0.0, tried=tried
        )
    )

    assert result is None
    reason = next(iter(tried.values()))
    assert "max_tokens=16 ran out on reasoning" in reason
    assert "content empty" not in reason
    # and it is classified apart from a model that genuinely returns nothing
    nothing = {
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ]
    }
    assert ns._empty_reply_reason(nothing) == "content empty, no tool_calls, finish_reason='stop'"
    assert ns._budget_spent_on_reasoning(_emptied_by_reasoning())
    assert not ns._budget_spent_on_reasoning(nothing)


def test_a_spent_budget_does_not_spend_the_toolless_retry(monkeypatch):
    """Property 3's live second line: a tools-off retry cannot buy tokens. It is skipped,
    and the log names the budget rather than blaming the tools."""
    client = _Backend(_emptied_by_reasoning())
    monkeypatch.setattr(streaming, "_http_client", client)
    req_body = {"tools": TOOLS, "stream": False, "max_tokens": 16}

    data, _started, _sent = asyncio.run(
        ns._retry_empty_toolless_first_answer(
            client,
            "http://ollama/v1/chat/completions",
            None,
            req_body,
            _emptied_by_reasoning(),
            "auto-daily",
            NEMOTRON,
            0.0,
        )
    )

    assert client.sent == []  # no second 16-token turn
    assert data["choices"][0]["message"]["content"] == ""


def test_the_toolless_retry_still_runs_when_the_engine_returned_nothing(monkeypatch):
    """The retry stays for its real cause: tools swallowing an answer."""
    empty = {
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
        ]
    }
    client = _Backend(
        {"choices": [{"index": 0, "message": {"content": "answer"}, "finish_reason": "stop"}]}
    )

    data, _started, sent = asyncio.run(
        ns._retry_empty_toolless_first_answer(
            client,
            "http://ollama/v1/chat/completions",
            None,
            {"tools": TOOLS},
            empty,
            "auto-daily",
            NEMOTRON,
            0.0,
        )
    )

    assert len(client.sent) == 1 and client.sent[0]["tools"] is None
    assert data["choices"][0]["message"]["content"] == "answer"


def test_every_hinted_backend_failing_gives_the_chat_ui_the_cause(monkeypatch):
    """Property 4: OWUI gets a message naming the model and the cause, not an empty answer."""
    from portal.platform.inference.router import handlers, no_answer

    guard, clients = _ns_run(monkeypatch, {"ollama-general": [_emptied_by_reasoning()]})
    monkeypatch.setattr(ns, "_http_client", clients["ollama-general"])

    async def no_alternative(*_a, **_kw):
        return None

    monkeypatch.setattr(no_answer, "alternative_workspace", no_alternative)
    no_answer.set_chat_ui({"user-agent": "Python/3.11 aiohttp/3.14.3"})

    response = asyncio.run(
        handlers._dispatch_non_streaming(
            [_ns_backend("ollama-general", "ollama", NEMOTRON)],
            {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 16},
            "auto-daily",
            "",
            False,
            0.0,
        )
    )
    no_answer.set_chat_ui({})

    text = json.loads(bytes(response.body))["choices"][0]["message"]["content"]
    assert qwen_not_substituted(text)
    assert NEMOTRON in text and "max_tokens=16 ran out on reasoning" in text
    assert "⚠️ The model did not produce an answer" not in text


def qwen_not_substituted(text: str) -> bool:
    return "No other model was substituted for it" in text
