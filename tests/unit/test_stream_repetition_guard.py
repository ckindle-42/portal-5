"""A repetition loop — output repeating WITHOUT PROGRESS — must end the stream
early, with a clear notice and a trace receipt, not burn the output budget.

Live receipts (2026-11-26/27) drive the definition: auto-coding::bigfix burned
8192 tokens repeating one line (must stop); s2-p2-auto-research cited one
source after each new claim and s4-auto-coding-core emitted a completed program
of rulers and ordinary code (both must pass). The QAT grader imports the same
rule from portal.platform.inference.router.text_repeat.
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


# ── guard semantics: repetition WITHOUT progress (the rule the QAT grader imports) ──

CITE_LINE = "Source: https://github.com/jundot/omlx/releases/tag/v0.8.1"
AI_LOOP_LINE = (
    "I am an AI assistant designed to provide information and assistance on various topics."
)


def _research_answer() -> str:
    """s2-p2-auto-research (live 2026-11-27): one citation after each distinct claim."""
    return "".join(
        f"- Finding {n}: oMLX v0.8.{n} added seat-level prefill memory guards for releases.\n"
        f"{CITE_LINE}\n"
        for n in range(1, 6)
    )


def _program() -> str:
    """s4-auto-coding-core (live 2026-11-27): a completed program of ordinary code."""
    ruler = "# " + "-" * 75
    parts: list[str] = []
    for name in ("load_inventory", "apply_patch", "sync_seats", "audit_blobs", "prune_models"):
        parts += [
            ruler,
            f"def {name}(rows: list[dict[str, str]]) -> dict[str, int]:",
            f'    """Normalize {name} rows and count the failures."""',
            "    failures = sum(",
            "        not bool(row.get('ok'))",
            "        for row in rows",
            "    )",
            "    return {'count': len(rows), 'failed': failures}",
            "",
        ]
    return "\n".join(parts)


def test_research_citation_after_each_new_claim_passes() -> None:
    guard = LineRepetitionGuard()
    assert not guard.feed(_research_answer())
    assert not guard.finish()
    assert guard.tripped_line is None


def test_completed_program_with_repeated_rulers_passes() -> None:
    guard = LineRepetitionGuard()
    assert not guard.feed(_program())
    assert not guard.finish()
    assert guard.tripped_line is None


def test_ai_assistant_loop_still_trips() -> None:
    """auto-coding::bigfix (live): the same line again and again, nothing new between."""
    guard = LineRepetitionGuard()
    assert not guard.feed("".join(f"{AI_LOOP_LINE}\n" for _ in range(REPEAT_LIMIT - 1)))
    assert not guard.feed(AI_LOOP_LINE)  # final line still unterminated in _pending
    assert guard.finish()
    assert guard.tripped_line == AI_LOOP_LINE
    assert guard.tripped_count == REPEAT_LIMIT


def test_short_cycle_dominating_tail_trips() -> None:
    a = "Backing up the deployment state before the next migration step begins now."
    b = "Waiting for the cluster to settle before the rollout continues any further."
    guard = LineRepetitionGuard()
    assert guard.feed("".join(f"{line}\n" for _ in range(4) for line in (a, b)))
    assert guard.tripped_line in (a, b)


def test_guard_trips_across_fragmented_deltas() -> None:
    guard = LineRepetitionGuard()
    fragments = [AI_LOOP_LINE[:32], AI_LOOP_LINE[32:] + "\n"] * REPEAT_LIMIT
    assert guard.feed("".join(fragments))
    assert guard.tripped_line == AI_LOOP_LINE


def test_distinct_and_short_lines_never_trip() -> None:
    guard = LineRepetitionGuard()
    for i in range(REPEAT_LIMIT * 3):
        assert not guard.feed(f"a distinct line of some length number {i}\n")
        assert not guard.feed("- item\n")  # below the min length
    assert guard.tripped_line is None


def test_guard_feed_after_trip_stays_tripped() -> None:
    guard = LineRepetitionGuard()
    assert guard.feed("".join(f"{AI_LOOP_LINE}\n" for _ in range(REPEAT_LIMIT)))
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
