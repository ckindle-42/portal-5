"""P-1: an empty streamed tool-loop hop gets one non-streamed retry that salvages a
malformed tool call. P-2: the model a request failed over from is not evicted."""

from __future__ import annotations

import asyncio

from portal.platform.inference import load_guard as lg
from portal.platform.inference.router import streaming

TOOLS = [
    {"type": "function", "function": {"name": "compliance_read", "parameters": {"type": "object"}}}
]


def test_a_protected_model_is_not_evicted_until_its_cool_down_ends():
    g = lg.LoadGuard(omlx_url=lambda: None, pinned=lambda: "")
    resident = {"a": 10, "b": 20}
    assert g._ollama_idle(resident) == 30.0
    g.protect(lg.OLLAMA, "b")
    assert g._ollama_idle(resident) == 10.0
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


def _msg(content="", tool_calls=None):
    return {"choices": [{"message": {"content": content, "tool_calls": tool_calls}}]}


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
    text, calls = _rescue(monkeypatch, client)
    assert client.sent["stream"] is False
    assert [c["function"]["name"] for c in calls] == ["compliance_read"] and text == ""


def test_proper_tool_calls_and_plain_answers_come_back_as_they_are(monkeypatch):
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "compliance_read", "arguments": "{}"},
    }
    assert _rescue(monkeypatch, _Client(_Resp(200, _msg("", [call])))) == ("", [call])
    assert _rescue(monkeypatch, _Client(_Resp(200, _msg("<think>x</think>The answer.")))) == (
        "The answer.",
        [],
    )


def test_a_failed_rescue_falls_back_to_the_no_answer_path(monkeypatch):
    assert _rescue(monkeypatch, _Client(exc=OSError("down"))) == ("", [])
    assert _rescue(monkeypatch, _Client(_Resp(500, {}))) == ("", [])
