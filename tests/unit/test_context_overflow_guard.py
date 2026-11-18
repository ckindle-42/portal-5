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

import copy
import hashlib
import json
import logging
import typing
from pathlib import Path

import pytest
import yaml

from portal.platform.inference.router import context_budget as cb
from portal.platform.inference.router import streaming, truncation

BIG_RESULT = "PAGE-HEAD\n" + "telemetry row\n" * (112 * 1024 // 14) + "PAGE-TAIL"

SYSTEM = "SYSTEM-CONTRACT-MARKER: you are the security reviewer."

QUESTION = "Review the last 24 hours of telemetry."

TOOLS = [
    {
        "type": "function",
        "function": {"name": "review_result", "parameters": {"type": "object"}},
    }
]


@pytest.fixture(autouse=True)
def _isolate_truncation_state() -> typing.Iterator[None]:
    """The truncation estimate and notice are ContextVars shared by the whole test context."""
    truncation.set_estimate({"messages": []})
    yield
    truncation.set_estimate({"messages": []})


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


def _one_warning(caplog: pytest.LogCaptureFixture, marker: str) -> str:
    hits = [r.getMessage() for r in caplog.records if marker in r.getMessage()]
    assert len(hits) == 1, hits
    return hits[0]


def test_estimate_is_conservative_and_counts_tools() -> None:
    body = _live_body()
    assert cb.estimate_tokens(body, "ollama") > len(BIG_RESULT) // 4  # erring high
    without_tools = {**body, "tools": None}
    assert cb.estimate_tokens(body, "ollama") > cb.estimate_tokens(without_tools, "ollama")


def test_the_unfitted_prompt_is_the_one_ollama_cuts_the_head_off() -> None:
    """Ollama keeps the tail of an over-long prompt: the system prompt and question die."""
    body = _live_body()
    estimated = cb.estimate_tokens(body, "ollama")
    assert estimated > 8192, "the live turn must be one the engine would have truncated"
    # What an 8k window of tail-only prompt would actually carry.
    tail = "".join(str(m.get("content") or "") for m in body["messages"])[-8192 * 4 :]
    assert SYSTEM not in tail and QUESTION not in tail
    assert "PAGE-TAIL" in tail  # only the context-free end of the tool result survives


def test_a_fitted_prompt_is_not_reported_as_an_engine_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live 2026-11-16: the guard fitted the prompt, then the stale pre-fit estimate
    produced `⚠️ Input truncated: about 22,559 tokens…` over an answer that had been
    fitted to 5,996. After a fit the notice names the guard's own cut, nothing else."""
    workspace = "ws-notice-fit"
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    body = _live_body()
    truncation.set_estimate(body)  # request start: the pre-fit size
    chars = len(json.dumps(body["messages"])) + len(json.dumps(body["tools"]))
    assert chars // 4 > 8192 * 1.25  # the old check fired on exactly this

    cb.fit_prompt(body, workspace_id=workspace, model="granite4.1:8b-ctx8k", engine="ollama")

    assert not truncation.check("granite4.1:8b-ctx8k", workspace, 4656)  # what Ollama reported
    notice = truncation.take_notice()
    assert "Input truncated" not in notice and "22,559" not in notice
    assert "shortened" in notice and "8,192" in notice and "tool message 3" in notice
    assert truncation.take_notice() == ""


def _persona_prompt() -> str:
    data = yaml.safe_load(Path("config/personas/securityreviewer.yaml").read_text())
    return str(data["system_prompt"])


def test_the_security_reviewer_persona_survives_the_fit_byte_identical(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The live probe's turn: the real persona YAML, ~95 KB of user history, the question."""
    monkeypatch.setattr(cb, "workspace_context_limit", lambda _ws: 8192)
    persona = _persona_prompt()
    question = "In one sentence: what is your role?"
    body = {
        "model": "granite4.1:8b-ctx8k",
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": persona},
            {"role": "user", "content": "HISTORY-USER " + "telemetry row\n" * 4_300},
            {"role": "assistant", "content": "HISTORY-ANSWER " + "notable row\n" * 3_000},
            {"role": "user", "content": question},
        ],
    }
    assert sum(len(str(m["content"])) for m in body["messages"]) > 95_000

    with caplog.at_level(logging.DEBUG, logger=cb.__name__):
        report = cb.fit_prompt(
            body, workspace_id="ws-persona", model="granite4.1:8b-ctx8k", engine="ollama"
        )

    assert report.fitted and report.estimated_after <= report.budget
    assert body["messages"][0]["content"] == persona  # byte-identical, still first
    assert body["messages"][-1]["content"] == question
    assert len(body["messages"]) == 4  # nothing dropped
    assert "truncated" in body["messages"][1]["content"]
    assert "truncated" in body["messages"][2]["content"]
    digest = hashlib.sha256(persona.encode()).hexdigest()[:12]
    warning = _one_warning(caplog, "Context fit:")
    assert f"system={len(persona)} chars sha256={digest}" in warning  # the INFO receipt
    sent = next(
        r.getMessage() for r in caplog.records if r.getMessage().startswith("Context body:")
    )
    assert f"system={len(persona)} chars sha256={digest}" in sent
    assert "You coordinate Portal's grounded security review" in sent
    assert "system:" in sent and "limit=8192" in sent


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


TRACE_SEATS = [
    ("auto-daily", "hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx32k"),
    ("auto-general-uncensored::throwaway-ornith15", "portal5/ornith15-35b:q4_K_M-ctx256k"),
]


def _trace_body(model: str) -> dict[str, typing.Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "stream": True,
        "max_tokens": 24,
        "stream_options": {"include_usage": True},
    }


@pytest.mark.anyio
@pytest.mark.parametrize(("workspace", "model"), TRACE_SEATS)
async def test_the_trace_turn_reaches_the_engine_byte_identical(
    workspace: str,
    model: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Live 2026-11-16 (dbb943418): two trace seats failed with tokens=0 and no `Context
    fit` line. A 24-token turn fits every seat window, so the guard must hand the engine
    exactly the body the pre-guard revision did — num_ctx, num_predict, think, order."""
    from portal.platform.inference.router.validation import _inject_ollama_options

    client = _StreamClient([_Resp(["data: [DONE]"])])
    monkeypatch.setattr(streaming, "_http_client", client)
    monkeypatch.setattr(streaming, "_backend_type_for_url", lambda _url: "ollama")
    injected = _inject_ollama_options(_trace_body(model), workspace)
    snapshot = copy.deepcopy(injected)

    with caplog.at_level(logging.WARNING, logger=cb.__name__):
        report = cb.fit_prompt(injected, workspace_id=workspace, model=model, engine="ollama")
        async for _chunk in streaming._tool_loop_frames(
            "http://ollama:11434/v1/chat/completions", injected, workspace, model, "", set()
        ):
            pass

    assert report.limit is not None and report.estimated_after < report.budget
    assert not report.fitted and injected == snapshot
    assert client.bodies == [snapshot]  # what the engine was actually sent
    assert not [r for r in caplog.records if "Context fit:" in r.getMessage()]
