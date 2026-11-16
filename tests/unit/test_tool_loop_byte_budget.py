"""Tool results stay within the context-derived byte budget across loop hops."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router.tool_repeat import (
    FINAL_ANSWER_REQUEST,
    apply_tool_byte_budget,
    tool_result_byte_budget,
)

_DOCUMENT = "Invoice line\n" * 2000  # 26_000 bytes, above the rejected 4_000-char cap
_WALK = "A" * 600


def test_budget_is_half_the_window_at_two_bytes_per_token() -> None:
    assert tool_result_byte_budget(0) == 0
    assert tool_result_byte_budget(-1) == 0
    # 50% × 2 bytes/token = one byte of tool content per declared token.
    assert tool_result_byte_budget(8192) == 8192
    assert tool_result_byte_budget(98304) == 98304
    assert tool_result_byte_budget(98304) > len(_DOCUMENT.encode("utf-8"))


def test_budget_truncates_new_tool_results_to_remaining_bytes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    exact_message = {"role": "tool", "content": "x" * 100}
    exact = apply_tool_byte_budget(0, [exact_message], 100, "ws")
    assert exact == 100 and exact_message["content"] == "x" * 100
    ignored = apply_tool_byte_budget(0, [{"role": "assistant", "content": "x" * 500}], 10, "ws")
    assert ignored == 0
    multibyte_message = {"role": "tool", "content": "é" * 100}
    multibyte = apply_tool_byte_budget(0, [multibyte_message], 80, "ws")
    assert multibyte == 80
    assert len(multibyte_message["content"].encode("utf-8")) == 80
    assert "truncated" in multibyte_message["content"]
    small_message = {"role": "tool", "content": "prefix" * 20}
    small = apply_tool_byte_budget(0, [small_message], 40, "ws")
    assert small == 40
    assert small_message["content"].startswith("prefix")
    assert small_message["content"].endswith("[cut:budget]")
    caplog.clear()
    first = apply_tool_byte_budget(0, [{"role": "tool", "content": _WALK}], 1000, "ws")
    assert first == 600
    second_message = {"role": "tool", "content": "B" * 600}
    second = apply_tool_byte_budget(first, [second_message], 1000, "ws")
    assert second == 1000
    assert len(second_message["content"].encode("utf-8")) == 400
    hits = [r for r in caplog.records if "result truncated" in r.message]
    assert len(hits) == 1
    assert "accumulated=1200" in hits[0].message and "budget=1000" in hits[0].message


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


def _tool_frame(args: dict[str, str], name: str = "execute_python") -> _Resp:
    call = {"index": 0, "id": "c", "function": {"name": name, "arguments": json.dumps(args)}}
    chunk = {"choices": [{"delta": {"tool_calls": [call]}, "finish_reason": "tool_calls"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _answer_frame(text: str) -> _Resp:
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def _run_stream(
    monkeypatch: pytest.MonkeyPatch,
    frames: list[_Resp],
    contents: list[str],
    context_limit: int,
    *,
    body_messages: list[dict] | None = None,
    max_hops: int | None = None,
) -> list[dict]:
    bodies: list[dict] = []
    pending_frames = list(frames)
    pending_contents = list(contents)

    class _Client:
        def stream(self, method: str, url: str, json: dict | None = None):  # noqa: A002
            bodies.append(copy.deepcopy(json))
            return _Stream(pending_frames.pop(0))

    async def fake_dispatch(tc: dict, *_a: object, **_k: object) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "name": tc["function"]["name"],
            "content": pending_contents.pop(0),
        }

    monkeypatch.setattr(streaming, "_http_client", _Client())
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda url: "omlx")
    monkeypatch.setattr(streaming, "_dispatch_tool_call", fake_dispatch)
    monkeypatch.setattr(streaming, "workspace_context_limit", lambda _ws: context_limit)

    body = {
        "messages": body_messages or [{"role": "user", "content": "hi"}],
        "model": "m",
        "tools": [
            {"type": "function", "function": {"name": "execute_python", "parameters": {}}},
            {"type": "function", "function": {"name": "read_pdf", "parameters": {}}},
        ],
    }
    if max_hops is not None:
        body["portal_bite_max_hops"] = max_hops

    async def run() -> None:
        async for _chunk in streaming._tool_loop_frames(
            "http://omlx.test/v1/chat/completions",
            body,
            "ws-budget",
            "m",
            "",
            {"execute_python", "read_pdf"},
        ):
            pass

    asyncio.run(run())
    return bodies


def _tool_contents(body: dict) -> list[str]:
    return [m["content"] for m in body["messages"] if m.get("role") == "tool"]


def test_streaming_budget_truncates_results_and_keeps_tools_available(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    bodies = _run_stream(
        monkeypatch,
        [
            _tool_frame({"code": "walk-1"}),
            _tool_frame({"code": "walk-2"}),
            _answer_frame("done"),
        ],
        [_WALK, "B" * 600],
        1000,
    )
    assert bodies[1]["tools"]
    assert _tool_contents(bodies[1]) == [_WALK]
    assert bodies[2]["tools"] and bodies[2]["tool_choice"] is None
    result_contents = _tool_contents(bodies[2])
    assert result_contents[0] == _WALK
    assert len(result_contents[1].encode("utf-8")) == 400
    assert "truncated" in result_contents[1].lower()
    assert "budget" in result_contents[1].lower()
    hits = [r for r in caplog.records if "result truncated" in r.message]
    assert len(hits) == 1 and "accumulated=1200" in hits[0].message


def test_streaming_document_under_budget_passes_through_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = _run_stream(
        monkeypatch,
        [_tool_frame({"file_path": "/workspace/uploads/doc.pdf"}, "read_pdf"), _answer_frame("ok")],
        [_DOCUMENT],
        98304,
    )
    assert bodies[1]["tools"]
    assert _tool_contents(bodies[1]) == [_DOCUMENT]
    assert FINAL_ANSWER_REQUEST not in bodies[1]["messages"]


def test_streaming_no_tool_and_small_tool_turns_match_an_unbudgeted_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_tool_off = _run_stream(monkeypatch, [_answer_frame("hello")], [], 0)
    no_tool_on = _run_stream(monkeypatch, [_answer_frame("hello")], [], 98304)
    assert no_tool_off == no_tool_on

    small_off = _run_stream(
        monkeypatch,
        [_tool_frame({"code": "print(1)"}), _answer_frame("yes")],
        ["ok"],
        0,
    )
    small_on = _run_stream(
        monkeypatch,
        [_tool_frame({"code": "print(1)"}), _answer_frame("yes")],
        ["ok"],
        98304,
    )
    assert small_off == small_on
    assert small_on[1]["tools"]
    assert _tool_contents(small_on[1]) == ["ok"]


class _NSClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.bodies: list[dict] = []

    async def post(self, url: str, json: dict, timeout: object) -> httpx.Response:  # noqa: A002
        self.bodies.append(copy.deepcopy(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _ns_tool_reply(args: dict[str, str], name: str = "execute_python") -> httpx.Response:
    call = {
        "id": "c",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [call]}}]},
    )


def _ns_text_reply(text: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": text}}]}
    )


def _arm_non_stream(monkeypatch: pytest.MonkeyPatch, context_limit: int) -> str:
    from portal.platform.inference import tool_registry as registry_mod

    ws = "ws-budget"
    monkeypatch.setitem(ns.WORKSPACES, ws, {"model_hint": "m"})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: True)
    monkeypatch.setattr(ns, "_resolve_persona_tools", lambda *_a: ["execute_python", "read_pdf"])
    monkeypatch.setattr(ns, "apply_eval_scope", lambda _b, tools: tools)
    monkeypatch.setattr(ns, "workspace_context_limit", lambda _ws: context_limit)

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
    return ws


async def _run_non_stream(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[httpx.Response],
    contents: list[str],
    context_limit: int,
    *,
    body_messages: list[dict] | None = None,
    max_hops: int = 20,
) -> list[dict]:
    ws = _arm_non_stream(monkeypatch, context_limit)
    pending = list(contents)

    async def dispatch(tc: dict, *_a: object, **_k: object) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tc.get("id"),
            "name": tc["function"]["name"],
            "content": pending.pop(0),
        }

    monkeypatch.setattr(ns, "_dispatch_tool_call", dispatch)
    client = _NSClient(list(responses))
    monkeypatch.setattr(ns, "_http_client", client)
    backend = SimpleNamespace(
        id="b",
        type="ollama",
        chat_url="http://b/v1/chat/completions",
        models=["m"],
        resolve_model=lambda h: h,
    )
    await ns._try_non_streaming(
        backend,
        {"messages": body_messages or [{"role": "user", "content": "hi"}]},
        ws,
        0.0,
        max_hops=max_hops,
    )
    return client.bodies


def test_streaming_oversized_result_is_truncated_and_tools_remain_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = _run_stream(
        monkeypatch,
        [_tool_frame({"code": "large"}), _tool_frame({"code": "next"}), _answer_frame("done")],
        ["A" * 1200, "small result"],
        1000,
    )

    assert len(bodies) == 3
    assert bodies[1]["tools"]
    first_result = _tool_contents(bodies[1])[0]
    assert len(first_result.encode("utf-8")) <= 1000
    assert "truncated" in first_result.lower() and "budget" in first_result.lower()
    assert bodies[2]["tools"]
    assert bodies[2]["messages"][-2]["tool_calls"][0]["function"]["name"] == "execute_python"


def test_streaming_budget_cap_finalizer_keeps_the_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = {"role": "system", "content": "Security reviewer system instructions."}
    bodies = _run_stream(
        monkeypatch,
        [
            _tool_frame({"code": "large"}),
            _tool_frame({"code": "at-cap"}),
            _answer_frame("done"),
        ],
        ["A" * 1200],
        1000,
        body_messages=[system, {"role": "user", "content": "investigate"}],
        max_hops=2,
    )

    assert len(bodies) == 3
    finalizer = bodies[1]
    assert finalizer["tools"]
    assert finalizer["messages"][0] == system
    finalizer = bodies[2]
    assert finalizer["tools"] is None and finalizer["tool_choice"] is None
    assert finalizer["messages"][0] == system
    assert finalizer["messages"][-1] == FINAL_ANSWER_REQUEST


@pytest.mark.anyio
async def test_nonstreaming_oversized_result_is_truncated_and_tools_remain_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = await _run_non_stream(
        monkeypatch,
        [
            _ns_tool_reply({"code": "large"}),
            _ns_tool_reply({"code": "next"}),
            _ns_text_reply("done"),
        ],
        ["A" * 1200, "small result"],
        1000,
    )

    assert len(bodies) == 3
    assert bodies[1]["tools"]
    first_result = _tool_contents(bodies[1])[0]
    assert len(first_result.encode("utf-8")) <= 1000
    assert "truncated" in first_result.lower() and "budget" in first_result.lower()
    assert bodies[2]["tools"]
    assert bodies[2]["messages"][-2]["tool_calls"][0]["function"]["name"] == "execute_python"


@pytest.mark.anyio
async def test_nonstreaming_hop_limit_finalizer_keeps_the_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = {"role": "system", "content": "Security reviewer system instructions."}
    bodies = await _run_non_stream(
        monkeypatch,
        [_ns_tool_reply({"code": "print(1)"}), _ns_text_reply("done")],
        ["ok"],
        1000,
        body_messages=[system, {"role": "user", "content": "investigate"}],
        max_hops=1,
    )

    assert len(bodies) == 2
    finalizer = bodies[1]
    assert finalizer["tools"] is None and finalizer["tool_choice"] is None
    assert finalizer["messages"][0] == system


@pytest.mark.anyio
async def test_nonstreaming_budget_truncates_results_and_keeps_tools_available(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    bodies = await _run_non_stream(
        monkeypatch,
        [
            _ns_tool_reply({"code": "walk-1"}),
            _ns_tool_reply({"code": "walk-2"}),
            _ns_text_reply("done"),
        ],
        [_WALK, "B" * 600],
        1000,
    )
    assert bodies[1]["tools"]
    assert _tool_contents(bodies[1]) == [_WALK]
    assert bodies[2]["tools"] and bodies[2]["tool_choice"] == "auto"
    result_contents = _tool_contents(bodies[2])
    assert result_contents[0] == _WALK
    assert len(result_contents[1].encode("utf-8")) == 400
    assert "truncated" in result_contents[1].lower()
    assert "budget" in result_contents[1].lower()
    hits = [r for r in caplog.records if "result truncated" in r.message]
    assert len(hits) == 1 and "accumulated=1200" in hits[0].message


@pytest.mark.anyio
async def test_nonstreaming_document_under_budget_passes_through_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = await _run_non_stream(
        monkeypatch,
        [
            _ns_tool_reply({"file_path": "/workspace/uploads/doc.pdf"}, "read_pdf"),
            _ns_text_reply("ok"),
        ],
        [_DOCUMENT],
        98304,
    )
    assert bodies[1]["tools"]
    assert _tool_contents(bodies[1]) == [_DOCUMENT]
    assert FINAL_ANSWER_REQUEST not in bodies[1]["messages"]


@pytest.mark.anyio
async def test_nonstreaming_no_tool_and_small_tool_turns_match_an_unbudgeted_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_tool_off = await _run_non_stream(monkeypatch, [_ns_text_reply("hello")], [], 0)
    no_tool_on = await _run_non_stream(monkeypatch, [_ns_text_reply("hello")], [], 98304)
    assert no_tool_off == no_tool_on

    small_off = await _run_non_stream(
        monkeypatch,
        [_ns_tool_reply({"code": "print(1)"}), _ns_text_reply("yes")],
        ["ok"],
        0,
    )
    small_on = await _run_non_stream(
        monkeypatch,
        [_ns_tool_reply({"code": "print(1)"}), _ns_text_reply("yes")],
        ["ok"],
        98304,
    )
    assert small_off == small_on
    assert small_on[1]["tools"]
    assert _tool_contents(small_on[1]) == ["ok"]
