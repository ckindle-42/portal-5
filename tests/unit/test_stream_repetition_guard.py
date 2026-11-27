"""A degenerate line-repetition loop must end the stream early, with a clear
notice and a trace receipt — not burn the full output budget silently.

Seen live 2026-11-26 on auto-coding::bigfix: Qwen3-Coder-30B-A3B-Instruct-4bit
generated 8192 tokens in 119.39s (finish_reason=length) repeating one line; the
QAT grader flagged it after the fact. The wire sampling for that seat is
card-correct (captured below), so the guard is the missing property: stop the
runaway generation in-stream.
"""

from __future__ import annotations

import json
import typing
from unittest.mock import MagicMock

import pytest

import portal.platform.inference.router.streaming as st
from portal.platform.inference.router.correlation import set_correlation_id
from portal.platform.inference.router.text_repeat import REPEAT_LIMIT, LineRepetitionGuard

DONE = b"data: [DONE]\n\n"
LOOP_LINE = "Analyzing endpoint compliance status across the managed BigFix inventory\n"
SENTINEL = "SENTINEL-AFTER-TRIP"


def _delta(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"index": 0, "delta": {"content": content}}]})


class _Resp:
    def __init__(self, lines: list[str], status: int = 200) -> None:
        self.status_code = status
        self._lines = lines

    async def aiter_lines(self) -> typing.AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _Ctx:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _Resp:
        return self._resp

    async def __aexit__(self, *_: typing.Any) -> None:
        return None


@pytest.fixture
def stream_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    monkeypatch.setattr(st, "_http_client", client)
    return client


@pytest.fixture(autouse=True)
def _correlation_id() -> typing.Iterator[None]:
    set_correlation_id("corr-repetition-test")
    yield
    set_correlation_id("")


def _serve(client: MagicMock, *responses: _Resp) -> None:
    queue = list(responses)
    client.stream.side_effect = lambda *_a, **_k: _Ctx(queue.pop(0))


async def _drain(gen: typing.AsyncIterator[bytes]) -> list[bytes]:
    return [c async for c in gen]


def _payloads(chunks: list[bytes]) -> list[dict[str, typing.Any]]:
    out = []
    for c in chunks:
        for line in c.decode().splitlines():
            if line.startswith("data: ") and line[6:] != "[DONE]":
                out.append(json.loads(line[6:]))
    return out


def _content(chunks: list[bytes]) -> str:
    return "".join(
        (ch.get("delta") or {}).get("content") or ""
        for p in _payloads(chunks)
        for ch in p.get("choices") or []
    )


# ── guard semantics (mirrors the QAT grader's degenerate-line definition) ──


def test_guard_trips_on_limit_th_identical_line() -> None:
    guard = LineRepetitionGuard()
    for _ in range(REPEAT_LIMIT - 1):
        assert not guard.feed(LOOP_LINE)
    assert guard.feed(LOOP_LINE)
    assert guard.tripped_line == LOOP_LINE.strip()


def test_guard_ignores_short_lines_and_distinct_lines() -> None:
    guard = LineRepetitionGuard()
    for _ in range(REPEAT_LIMIT * 2):
        assert not guard.feed("- item\n")  # below the min length
    for i in range(REPEAT_LIMIT * 2):
        assert not guard.feed(f"a distinct line of some length number {i}\n")


def test_guard_counts_across_fragmented_deltas() -> None:
    guard = LineRepetitionGuard()
    fragments = [LOOP_LINE[:20], LOOP_LINE[20:]] * (REPEAT_LIMIT - 1)
    assert not any(guard.feed(f) for f in fragments)
    assert guard.feed(LOOP_LINE[:20]) or guard.feed(LOOP_LINE[20:])
    assert guard.tripped_line == LOOP_LINE.strip()


def test_guard_feed_after_trip_stays_tripped() -> None:
    guard = LineRepetitionGuard()
    for _ in range(REPEAT_LIMIT):
        guard.feed(LOOP_LINE)
    assert guard.feed("anything else\n")


@pytest.mark.parametrize(
    "structural_line",
    [
        "# ---------------------------------------------------------------------------\n",
        "// ==========================================================================\n",
        "-----------------------------------------------------------------------------\n",
        "| --- | :---: | ---: |\n",
        "+--------------+--------------+--------------+\n",
        "```typescript\n",
        "~~~javascript\n",
        "/* *********************************************************************** */\n",
    ],
)
def test_guard_ignores_structural_lines(structural_line: str) -> None:
    guard = LineRepetitionGuard()
    for _ in range(REPEAT_LIMIT * 2):
        assert not guard.feed(structural_line)
    assert guard.tripped_line is None


def test_guard_still_catches_real_prose_loop() -> None:
    guard = LineRepetitionGuard()
    prose = "I am an AI assistant designed to help users with their questions.\n"
    for _ in range(REPEAT_LIMIT - 1):
        assert not guard.feed(prose)
    assert guard.feed(prose)
    assert guard.tripped_line == prose.strip()
    assert guard.tripped_count == REPEAT_LIMIT


# ── tool-loop streaming path (what auto-coding::bigfix runs on) ──


def _loop_lines() -> list[str]:
    return [_delta(LOOP_LINE) for _ in range(REPEAT_LIMIT)] + [_delta(f"\n{SENTINEL}\n")]


@pytest.mark.anyio
async def test_tool_loop_stops_degenerate_repetition(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(st, "_record_error", lambda ws, kind: recorded.append((ws, kind)))
    _serve(stream_client, _Resp([*_loop_lines(), "data: [DONE]"]))

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://x/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}]},
            "auto-coding::bigfix",
            "m",
            "p",
            {"web_search"},
        )
    )

    text = _content(chunks)
    assert SENTINEL not in text  # the backend was abandoned at the trip, not drained
    assert "repetition" in text.lower()  # the client-visible notice says why it ended
    reasons = [
        ch["finish_reason"]
        for p in _payloads(chunks)
        for ch in p.get("choices") or []
        if ch.get("finish_reason")
    ]
    assert reasons == ["stop"]
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE
    assert recorded == [("auto-coding::bigfix", "repetition_stop")]
    assert stream_client.stream.call_count == 1
    assert stream_client.post.call_count == 0  # no empty-hop rescue after the trip


@pytest.mark.anyio
async def test_tool_loop_normal_repeats_under_limit_pass_through(
    stream_client: MagicMock,
) -> None:
    lines = [_delta(LOOP_LINE) for _ in range(REPEAT_LIMIT - 1)] + [_delta(SENTINEL + "\n")]
    _serve(stream_client, _Resp([*lines, "data: [DONE]"]))

    chunks = await _drain(
        st._stream_with_tool_loop_impl(
            "http://x/v1/chat/completions",
            {"messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}]},
            "ws",
            "m",
            "p",
            {"web_search"},
        )
    )

    assert SENTINEL in _content(chunks)
    assert chunks.count(DONE) == 1


# ── toolless relay path (same property, no tools offered) ──


@pytest.mark.anyio
async def test_toolless_stream_stops_degenerate_repetition(
    stream_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(st, "_record_error", lambda ws, kind: recorded.append((ws, kind)))
    _serve(stream_client, _Resp([*_loop_lines(), "data: [DONE]"]))

    chunks = await _drain(
        st._stream_from_backend_guarded("http://x/v1/chat/completions", {}, "ws", "m")
    )

    text = _content(chunks)
    assert SENTINEL not in text
    assert "repetition" in text.lower()
    assert recorded == [("ws", "repetition_stop")]
    reasons = [
        ch["finish_reason"]
        for p in _payloads(chunks)
        for ch in p.get("choices") or []
        if ch.get("finish_reason")
    ]
    assert reasons == ["stop"]
    assert chunks.count(DONE) == 1 and chunks[-1] == DONE


# ── wire-sampling capture: what actually reaches oMLX for a bigfix turn ──


def test_bigfix_omlx_wire_body_carries_card_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-level capture of the outbound oMLX payload for auto-coding::bigfix.

    Production order: routing resolves the seat alias to the served oMLX id,
    ``_inject_omlx_options`` merges the variant config. The qwen3-coder card is
    temperature 0.7 / top_p 0.8 / top_k 20 / repeat_penalty 1.05; every card key
    must reach the wire with exactly that value, no presence_penalty, no think
    injection, and the 8192 default output cap.
    """
    from portal.platform.inference.cluster_backends import DEFAULT_CONFIG_PATH, BackendRegistry
    from portal.platform.inference.config import load_portal_config, merge_workspace_variant
    from portal.platform.inference.model_cards import card_sampling
    from portal.platform.inference.router import validation
    from portal.platform.inference.router.workspaces import WORKSPACES

    served = "Qwen3-Coder-30B-A3B-Instruct-4bit"
    spec = load_portal_config().workspaces["auto-coding"]
    merged = merge_workspace_variant(dict(WORKSPACES["auto-coding"]), spec.variants["bigfix"])
    monkeypatch.setattr(
        validation, "WORKSPACES", {**dict(WORKSPACES), "auto-coding::bigfix": merged}
    )
    monkeypatch.setattr(validation, "registry", BackendRegistry(str(DEFAULT_CONFIG_PATH)))

    body = {
        "model": served,
        "messages": [{"role": "user", "content": "In one sentence, who are you?"}],
        "stream": True,
    }
    out = validation._inject_omlx_options(dict(body), "auto-coding::bigfix")

    card = card_sampling(served, None)
    assert card == {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repeat_penalty": 1.05}
    assert out["temperature"] == card["temperature"]
    assert out["top_p"] == card["top_p"]
    assert out["top_k"] == card["top_k"]
    assert out["repetition_penalty"] == card["repeat_penalty"]
    assert "presence_penalty" not in out
    assert out["max_tokens"] == 8192
    assert "think" not in out
    assert "chat_template_kwargs" not in out
    assert out["stream_options"] == {"include_usage": True}
