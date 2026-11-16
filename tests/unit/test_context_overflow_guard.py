"""The Pipeline never sends a prompt larger than the seat's context window.

Live 2026-11-16, security-reviewer on ``granite4.1:8b-ctx8k`` (Ollama): a 112 KB tool
result went into the conversation and Ollama cut the prompt from the head to fit
``num_ctx``. The system prompt, the persona and the user's question were dropped and the
request reported 237 prompt tokens — no error, no log line. These tests hold the guard
that replaced that silence: the prompt is fitted before every engine call, the system
prompt and the latest user turn survive, one WARNING names what was shrunk, and a prompt
that cannot fit is refused in band.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import typing
from types import SimpleNamespace

import httpx
import pytest

from portal.platform.inference.router import context_budget as cb
from portal.platform.inference.router import non_streaming as ns
from portal.platform.inference.router import streaming
from portal.platform.inference.router.metrics import _REGISTRY

#: The live failure's payload: a 112 KB tool result in one conversation turn.
BIG_RESULT = "PAGE-HEAD\n" + "telemetry row\n" * (112 * 1024 // 14) + "PAGE-TAIL"
SYSTEM = "SYSTEM-CONTRACT-MARKER: you are the security reviewer."
QUESTION = "Review the last 24 hours of telemetry."
TOOLS = [
    {
        "type": "function",
        "function": {"name": "review_result", "parameters": {"type": "object"}},
    }
]


def _metric(workspace: str, engine: str, outcome: str) -> float:
    value = _REGISTRY.get_sample_value(
        "portal5_context_fit_total",
        {"workspace": workspace, "engine": engine, "outcome": outcome},
    )
    return float(value or 0.0)


def _turn_body() -> dict[str, typing.Any]:
    """The turn as it arrives from Open WebUI, before the tool loop runs."""
    return {
        "model": "granite4.1:8b-ctx8k",
        "max_tokens": 4096,
        "tools": copy.deepcopy(TOOLS),
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": QUESTION},
        ],
    }


def _live_body() -> dict[str, typing.Any]:
    """The security-reviewer turn after a tool call and its 112 KB result."""
    body = _turn_body()
    body["messages"].extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "review_result", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "c1",
                "name": "review_result",
                "content": BIG_RESULT,
            },
        ]
    )
    return body


def _messages(body: dict[str, typing.Any], role: str) -> list[dict[str, typing.Any]]:
    return [m for m in body["messages"] if m.get("role") == role]


def _one_warning(caplog: pytest.LogCaptureFixture, marker: str) -> str:
    hits = [r.getMessage() for r in caplog.records if marker in r.getMessage()]
    assert len(hits) == 1, hits
    return hits[0]


# ── the window, resolved from config ───────────────────────────────────


def test_window_uses_the_seat_declared_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    assert cb.context_window("security-reviewer", "granite4.1:8b-ctx8k", "ollama") == 8192
    assert cb.context_window("security-reviewer", "some-omlx-id", "omlx") == 8192


def test_window_falls_back_to_the_baked_tag_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 0)
    assert cb.context_window("ws", "granite4.1:8b-ctx8k", "ollama") == 8192
    assert cb.context_window("ws", "m:q4-CTX16K", "ollama") == 16384
    assert cb.context_window("ws", "plain-model", "ollama") is None


def test_window_takes_the_smaller_of_declared_and_baked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tag baked below the declared limit is what Ollama actually enforces."""
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 32768)
    assert cb.context_window("ws", "granite4.1:8b-ctx8k", "ollama") == 8192


def test_window_for_omlx_falls_back_to_the_model_card(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 0)
    assert cb.context_window("ws", "Qwen3.8-27B", "omlx") == 262144


# ── the estimate ───────────────────────────────────────────────────────


def test_estimate_is_conservative_and_counts_tools() -> None:
    body = _live_body()
    assert cb.estimate_tokens(body, "ollama") > len(BIG_RESULT) // 4  # erring high
    without_tools = {**body, "tools": None}
    assert cb.estimate_tokens(body, "ollama") > cb.estimate_tokens(without_tools, "ollama")


# ── the live collapse, reproduced ──────────────────────────────────────


def test_the_unfitted_prompt_is_the_one_ollama_cuts_the_head_off() -> None:
    """Ollama keeps the tail of an over-long prompt: the system prompt and question die."""
    body = _live_body()
    estimated = cb.estimate_tokens(body, "ollama")
    assert estimated > 8192, "the live turn must be one the engine would have truncated"
    # What an 8k window of tail-only prompt would actually carry.
    tail = "".join(str(m.get("content") or "") for m in body["messages"])[-8192 * 4 :]
    assert SYSTEM not in tail and QUESTION not in tail
    assert "PAGE-TAIL" in tail  # only the context-free end of the tool result survives


@pytest.mark.parametrize("engine", ["ollama", "omlx"])
def test_112kb_tool_result_is_fitted_and_the_system_prompt_survives(
    engine: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = f"ws-112kb-{engine}"
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    body = _live_body()
    before = cb.estimate_tokens(body, engine)
    assert before > 8192, "the live turn must be one the engine would have truncated"

    with caplog.at_level(logging.WARNING, logger=cb.__name__):
        report = cb.fit_prompt(
            body, workspace_id=workspace, model="granite4.1:8b-ctx8k", engine=engine
        )

    assert report.fitted and report.estimated == before
    assert report.limit == 8192 and report.estimated_after <= report.budget
    assert cb.estimate_tokens(body, engine) <= report.budget
    assert _messages(body, "system")[0]["content"] == SYSTEM
    assert _messages(body, "user")[0]["content"] == QUESTION
    assert body["tools"] == TOOLS
    tool = _messages(body, "tool")[0]
    assert tool["content"].startswith("PAGE-HEAD")
    assert "PAGE-TAIL" not in tool["content"]
    assert "truncated" in tool["content"] and "context window" in tool["content"]

    warning = _one_warning(caplog, "Context fit:")
    assert workspace in warning and "8192" in warning and "tool[3]" in warning
    assert _metric(workspace, engine, "shrunk") == 1


def test_the_system_prompt_is_never_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    long_system = "SYSTEM " + "rule\n" * 300  # older than the tool result
    body = {
        "model": "granite4.1:8b-ctx8k",
        "messages": [
            {"role": "system", "content": long_system},
            {"role": "tool", "content": "result " * 20000},
            {"role": "user", "content": QUESTION},
        ],
    }
    report = cb.fit_prompt(
        body, workspace_id="ws-system", model="granite4.1:8b-ctx8k", engine="ollama"
    )
    assert report.fitted
    assert body["messages"][0]["content"] == long_system
    assert len(body["messages"]) == 3  # nothing dropped, only cut
    assert body["messages"][1]["content"].startswith("result result")
    assert "truncated" in body["messages"][1]["content"]


def test_tool_results_are_given_up_before_the_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    old_question, old_answer = "old question " * 200, "old answer " * 200
    body = {
        "model": "granite4.1:8b-ctx8k",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": old_question},
            {"role": "assistant", "content": old_answer},
            {
                "role": "tool",
                "tool_call_id": "c1",
                "name": "review_result",
                "content": "row " * 40000,
            },
            {"role": "user", "content": QUESTION},
        ],
    }
    report = cb.fit_prompt(
        body, workspace_id="ws-order", model="granite4.1:8b-ctx8k", engine="ollama"
    )
    assert report.fitted
    tool = body["messages"][3]
    assert "truncated" in tool["content"]
    assert tool["tool_call_id"] == "c1" and tool["name"] == "review_result"
    assert body["messages"][1]["content"] == old_question
    assert body["messages"][2]["content"] == old_answer
    assert body["messages"][-1]["content"] == QUESTION


def test_old_turns_are_cut_only_when_the_tool_results_are_not_enough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 2048)
    body = {
        "model": "m-ctx2k",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "old question " * 400},
            {"role": "assistant", "content": "old answer " * 400},
            {"role": "tool", "tool_call_id": "c1", "content": "row " * 2000},
            {"role": "user", "content": QUESTION},
        ],
    }
    report = cb.fit_prompt(body, workspace_id="ws-order2", model="m-ctx2k", engine="ollama")
    assert report.fitted
    assert "truncated" in body["messages"][3]["content"]
    assert "truncated" in body["messages"][1]["content"]
    assert "truncated" in body["messages"][2]["content"]
    assert body["messages"][0]["content"] == SYSTEM
    assert body["messages"][-1]["content"] == QUESTION
    assert cb.estimate_tokens(body, "ollama") <= report.budget


def test_overflow_is_refused_in_band_rather_than_truncated(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = "ws-overflow-refused"
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    body = {
        "model": "granite4.1:8b-ctx8k",
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "x" * 200_000},
        ],
    }
    with (
        caplog.at_level(logging.WARNING, logger=cb.__name__),
        pytest.raises(cb.ContextOverflowError) as excinfo,
    ):
        cb.fit_prompt(body, workspace_id=workspace, model="granite4.1:8b-ctx8k", engine="ollama")

    assert "conversation exceeds this workspace's context" in str(excinfo.value)
    assert excinfo.value.limit == 8192 and excinfo.value.estimated > 8192
    assert body["messages"][1]["content"] == "x" * 200_000  # nothing was sent
    assert (
        _one_warning(caplog, "Context overflow:") and _metric(workspace, "ollama", "overflow") == 1
    )


def test_prompt_that_fits_is_left_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    body = {
        "model": "granite4.1:8b-ctx8k",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hi"}],
        "tools": copy.deepcopy(TOOLS),
    }
    snapshot = copy.deepcopy(body)
    report = cb.fit_prompt(body, workspace_id="ws-fits", model="m", engine="ollama")
    assert not report.fitted
    assert body == snapshot


def test_untagged_prompt_is_not_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 0)
    body = _live_body()
    snapshot = copy.deepcopy(body)
    report = cb.fit_prompt(body, workspace_id="ws-untagged", model="plain", engine="ollama")
    assert report.limit is None and not report.fitted
    assert body == snapshot


# ── streaming: no-tools path ───────────────────────────────────────────


class _Resp:
    def __init__(self, lines: list[str]) -> None:
        self.status_code = 200
        self._lines = lines

    async def aiter_lines(self) -> typing.AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _Stream:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *exc: object) -> None:
        return None


class _StreamClient:
    def __init__(self, responses: list[_Resp]) -> None:
        self.responses = responses
        self.bodies: list[dict[str, typing.Any]] = []

    def stream(self, method: str, url: str, json: dict | None = None) -> _Stream:  # noqa: A002
        self.bodies.append(copy.deepcopy(json or {}))
        return _Stream(self.responses.pop(0))


def _answer_frame(text: str) -> _Resp:
    chunk = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


@pytest.mark.anyio
async def test_stream_guard_fits_before_the_engine_call(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = "ws-stream-fit"
    client = _StreamClient([_answer_frame("answer")])
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "ollama")
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    body = _live_body()

    with caplog.at_level(logging.WARNING, logger=cb.__name__):
        chunks = [
            chunk
            async for chunk in streaming._stream_from_backend_guarded(
                "http://ollama:11434/v1/chat/completions", body, workspace, "granite4.1:8b-ctx8k"
            )
        ]

    assert len(client.bodies) == 1
    sent = client.bodies[0]
    assert _messages(sent, "system")[0]["content"] == SYSTEM
    assert "truncated" in _messages(sent, "tool")[0]["content"]
    assert _one_warning(caplog, "Context fit:") and workspace in _one_warning(
        caplog, "Context fit:"
    )
    assert b"answer" in b"".join(chunks)


@pytest.mark.anyio
async def test_stream_refuses_in_band_and_never_calls_the_engine(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = "ws-stream-overflow"
    client = _StreamClient([_answer_frame("answer")])
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "ollama")
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    body = {
        "model": "granite4.1:8b-ctx8k",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "x" * 200_000},
        ],
    }

    with caplog.at_level(logging.WARNING, logger=cb.__name__):
        chunks = [
            chunk
            async for chunk in streaming._stream_from_backend_guarded(
                "http://ollama:11434/v1/chat/completions", body, workspace, "granite4.1:8b-ctx8k"
            )
        ]

    text = b"".join(chunks).decode()
    assert client.bodies == []  # nothing reached the engine
    assert "conversation exceeds this workspace's context" in text
    assert text.rstrip().endswith("data: [DONE]")


# ── streaming: tool loop (the live hole — results grow inside the turn) ──


def _tool_frame(args: dict[str, str]) -> _Resp:
    call = {
        "index": 0,
        "id": "c1",
        "function": {"name": "review_result", "arguments": json.dumps(args)},
    }
    chunk = {"choices": [{"delta": {"tool_calls": [call]}, "finish_reason": "tool_calls"}]}
    return _Resp([f"data: {json.dumps(chunk)}", "data: [DONE]"])


def test_tool_loop_fits_every_hop_and_keeps_the_system_prompt(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = "ws-loop-fit"
    client = _StreamClient([_tool_frame({"q": "24h"}), _answer_frame("done")])
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "ollama")
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)

    async def dispatch(call: dict, *_a: object, **_k: object) -> dict[str, typing.Any]:
        return {
            "role": "tool",
            "tool_call_id": call.get("id"),
            "name": call["function"]["name"],
            "content": BIG_RESULT,
        }

    monkeypatch.setattr(streaming, "_dispatch_tool_call", dispatch)

    async def run() -> None:
        async for _chunk in streaming._tool_loop_frames(
            "http://ollama:11434/v1/chat/completions",
            _turn_body(),
            workspace,
            "granite4.1:8b-ctx8k",
            "",
            {"review_result"},
        ):
            pass

    with caplog.at_level(logging.WARNING, logger=cb.__name__):
        asyncio.run(run())

    assert len(client.bodies) == 2
    assert not _messages(client.bodies[0], "tool")  # first hop has no result yet
    second = client.bodies[1]
    assert _messages(second, "system")[0]["content"] == SYSTEM
    assert _messages(second, "user")[0]["content"] == QUESTION
    assert _messages(second, "tool")[0]["content"].startswith("PAGE-HEAD")
    assert "truncated" in _messages(second, "tool")[0]["content"]
    assert "PAGE-TAIL" not in _messages(second, "tool")[0]["content"]
    assert _one_warning(caplog, "Context fit:")
    assert _metric(workspace, "ollama", "shrunk") == 1


# ── non-streaming ─────────────────────────────────────────────────────


class _PostClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.bodies: list[dict[str, typing.Any]] = []

    async def post(self, url: str, json: dict, timeout: object) -> httpx.Response:  # noqa: A002
        self.bodies.append(copy.deepcopy(json))
        resp = self.responses.pop(0)
        resp.request = httpx.Request("POST", url)
        return resp


def _text_reply(text: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": text}}]}
    )


def _arm_workspace(monkeypatch: pytest.MonkeyPatch, workspace: str) -> None:
    monkeypatch.setitem(ns.WORKSPACES, workspace, {"model_hint": "granite4.1:8b-ctx8k"})
    monkeypatch.setattr(ns, "registry", SimpleNamespace(request_timeout=5.0))
    monkeypatch.setattr(ns, "_model_supports_tools", lambda _m: False)
    monkeypatch.setattr(ns, "_backend_type_for_url", lambda _url: "ollama")


@pytest.mark.anyio
async def test_non_streaming_fits_before_the_post(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    workspace = "ws-ns-fit"
    _arm_workspace(monkeypatch, workspace)
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    client = _PostClient([_text_reply("answer")])
    monkeypatch.setattr(ns, "_http_client", client)
    backend = SimpleNamespace(
        id="b", type="ollama", chat_url="http://ollama:11434/v1/chat/completions",
        models=["granite4.1:8b-ctx8k"], resolve_model=lambda hint: hint,
    )  # fmt: skip

    with caplog.at_level(logging.WARNING, logger=cb.__name__):
        result = await ns._try_non_streaming(backend, _live_body(), workspace, 0.0)

    assert result is not None
    sent = client.bodies[0]
    assert _messages(sent, "system")[0]["content"] == SYSTEM
    assert "truncated" in _messages(sent, "tool")[0]["content"]
    assert _one_warning(caplog, "Context fit:")
    assert _metric(workspace, "ollama", "shrunk") == 1


@pytest.mark.anyio
async def test_non_streaming_refuses_in_band_and_never_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = "ws-ns-overflow"
    _arm_workspace(monkeypatch, workspace)
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    client = _PostClient([_text_reply("answer")])
    monkeypatch.setattr(ns, "_http_client", client)
    backend = SimpleNamespace(
        id="b", type="ollama", chat_url="http://ollama:11434/v1/chat/completions",
        models=["granite4.1:8b-ctx8k"], resolve_model=lambda hint: hint,
    )  # fmt: skip
    body = {
        "model": "granite4.1:8b-ctx8k",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "x" * 200_000}],
    }  # fmt: skip
    tried: dict[tuple[str, str], str] = {}

    result = await ns._try_non_streaming(backend, body, workspace, 0.0, tried=tried)

    assert result is None
    assert client.bodies == []
    reason = next(iter(tried.values()))
    assert "conversation exceeds this workspace's context" in reason
