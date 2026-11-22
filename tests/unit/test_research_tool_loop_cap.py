"""A research turn that keeps calling web_search/web_fetch is capped and answered.

QAT s2-p2 (trace p5-ffd6e0d32061) ran 17 fetches inside one pipeline turn, then
Open WebUI's native tool loop issued more auto-research turns until the 600s
deadline. The cap withholds tools and asks for one cited answer.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

import portal.platform.inference.router.non_streaming as ns
import portal.platform.inference.router.streaming as streaming
from portal.platform.inference.config import (
    WorkspaceSpec,
    get_workspace_dict,
    load_portal_config,
    merge_workspace_variant,
)
from portal.platform.inference.router.tool_repeat import (
    CITED_SYNTHESIS_REQUEST,
    FINAL_ANSWER_REQUEST,
)


class _Resp:
    def __init__(self, lines: list[str]) -> None:
        self.status_code = 200
        self._lines = lines

    async def aiter_lines(self):
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
        {
            "index": i,
            "id": f"c{i}",
            "function": {"name": name, "arguments": json.dumps({"q": i})},
        }
        for i, name in enumerate(names)
    ]
    chunk = {"choices": [{"delta": {"tool_calls": calls}, "finish_reason": "tool_calls"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _answer(text: str) -> _Resp:
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _drive_stream(
    monkeypatch: pytest.MonkeyPatch, frames: list[_Resp], tools: set[str], body_tools: list[str]
):
    bodies: list[dict] = []
    executed: list[str] = []

    class _Client:
        def stream(self, method: str, url: str, json: dict | None = None):  # noqa: A002
            assert json is not None
            bodies.append(
                {
                    "tools": json.get("tools"),
                    "tool_choice": json.get("tool_choice"),
                    "messages": list(json["messages"]),
                }
            )
            return _Stream(frames.pop(0))

    async def fake_dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["name"])
        return {
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "name": tc["function"]["name"],
            "content": "SNIPPET",
        }

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "ollama")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)

    async def run() -> bytes:
        out = b""
        async for chunk in streaming._tool_loop_frames(
            "http://ollama.test/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": "what changed?"}],
                "model": "m",
                "tools": [{"type": "function", "function": {"name": name}} for name in body_tools],
            },
            "auto-research",
            "m",
            "",
            tools,
        ):
            out += chunk
        return out

    return asyncio.run(run()), bodies, executed


def _sse_tool_names(raw: bytes) -> list[str]:
    names: list[str] = []
    for line in raw.splitlines():
        if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
            continue
        payload = json.loads(line[6:])
        for choice in payload.get("choices") or []:
            for call in (choice.get("delta") or {}).get("tool_calls") or []:
                names.append(str((call.get("function") or {}).get("name") or ""))
    return names


def test_streaming_web_calls_past_the_cap_synthesize_a_cited_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming, "_configured_tool_calls", lambda _ws: 2)
    raw, bodies, executed = _drive_stream(
        monkeypatch,
        [
            _batch(["web_search", "web_fetch", "web_search", "web_fetch"]),
            _answer("Cited: the change shipped last week."),
        ],
        {"web_search", "web_fetch"},
        ["web_search", "web_fetch"],
    )

    assert executed == ["web_search", "web_fetch"]
    assert bodies[1]["tools"] is None
    assert bodies[1]["tool_choice"] == "none"
    assert bodies[1]["messages"][-1] == CITED_SYNTHESIS_REQUEST
    assert b"Cited: the change shipped last week." in raw
    assert _sse_tool_names(raw) == []
    assert b"Tool-use limit" not in raw


def test_streaming_cap_does_not_hand_client_tools_back_to_owui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming, "_configured_tool_calls", lambda _ws: 4)
    raw, bodies, executed = _drive_stream(
        monkeypatch,
        [_batch(["web_search", "client_search"]), _answer("Answered from the search.")],
        {"web_search"},
        ["web_search"],
    )

    assert executed == ["web_search"]
    assert _sse_tool_names(raw) == []
    assert bodies[1]["tool_choice"] == "none"
    assert b"Answered from the search." in raw


def test_streaming_hop_cap_synthesizes_instead_of_a_partial_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(streaming, "_configured_tool_calls", lambda _ws: None)
    monkeypatch.setattr(streaming, "_tool_hop_limit", lambda _ws, default=None: 1)
    raw, bodies, executed = _drive_stream(
        monkeypatch,
        [_batch(["web_search"]), _answer("Answered without another search.")],
        {"web_search"},
        ["web_search"],
    )

    assert executed == []
    assert bodies[1]["tools"] is None
    assert bodies[1]["tool_choice"] is None
    assert bodies[1]["messages"][-1] == FINAL_ANSWER_REQUEST
    assert b"Answered without another search." in raw
    assert b"Tool-use limit" not in raw


def _ns_backend() -> SimpleNamespace:
    return SimpleNamespace(
        id="b",
        type="ollama",
        chat_url="http://b/v1/chat/completions",
        models=["m"],
        resolve_model=lambda hint: hint,
    )


class _NSClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.bodies: list[dict] = []

    async def post(self, url: str, json: dict, timeout: object):  # noqa: A002
        self.bodies.append(dict(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _ns_batch(names: list[str]) -> httpx.Response:
    calls = [
        {
            "id": f"c{i}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps({"q": i})},
        }
        for i, name in enumerate(names)
    ]
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": calls}}]},
    )


@pytest.mark.anyio
async def test_nonstreaming_web_calls_past_the_cap_synthesize_a_cited_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portal.platform.inference import tool_registry as registry_mod

    ws = "research-cap"
    monkeypatch.setitem(ns.WORKSPACES, ws, {"model_hint": "m", "max_tool_calls": 2})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: ["web_search", "web_fetch"])
    monkeypatch.setattr(ns, "apply_eval_scope", lambda _b, tools: tools)

    async def refresh() -> None:
        return None

    monkeypatch.setattr(registry_mod.tool_registry, "refresh", refresh)
    monkeypatch.setattr(
        registry_mod.tool_registry,
        "get_openai_tools",
        lambda names: [
            {"type": "function", "function": {"name": n, "parameters": {}}} for n in names
        ],
    )
    executed: list[str] = []

    async def dispatch(tc, *_a, **_k):
        executed.append(tc["function"]["name"])
        return {"content": "SNIPPET"}

    monkeypatch.setattr(ns, "_dispatch_tool_call", dispatch)
    client = _NSClient(
        [
            _ns_batch(["web_search", "web_fetch", "web_search", "web_fetch"]),
            httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "Cited answer."}}]},
            ),
        ]
    )
    monkeypatch.setattr(ns, "_http_client", client)

    result = await ns._try_non_streaming(
        _ns_backend(),
        {"messages": [{"role": "user", "content": "what changed?"}]},
        ws,
        0.0,
        max_hops=5,
    )

    body = json.loads(result.body)
    assert executed == ["web_search", "web_fetch"]
    assert body["choices"][0]["message"]["content"] == "Cited answer."
    assert not body["choices"][0]["message"].get("tool_calls")
    assert client.bodies[1]["tools"] is None
    assert client.bodies[1]["tool_choice"] == "none"
    assert client.bodies[1]["messages"][-1] == CITED_SYNTHESIS_REQUEST


def test_auto_research_declares_the_call_cap_and_data_does_not() -> None:
    config = load_portal_config(_force_reload=True)
    catalog = get_workspace_dict(config)
    assert catalog["auto-research"]["max_tool_calls"] == 6
    assert catalog["auto-research"]["max_tool_hops"] == 4
    merged = merge_workspace_variant(
        catalog["auto-research"], config.workspaces["auto-research"].variants["data"]
    )
    assert merged.get("max_tool_calls") is None
    assert merged.get("max_tool_hops") is None


@pytest.mark.parametrize("max_tool_calls", [0, -1, True, "6"])
def test_max_tool_calls_must_be_a_positive_integer(max_tool_calls: object) -> None:
    with pytest.raises(ValueError):
        WorkspaceSpec.model_validate(
            {
                "name": "Research",
                "description": "Research",
                "module": "research",
                "max_tool_calls": max_tool_calls,
            }
        )
