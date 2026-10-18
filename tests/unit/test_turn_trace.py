"""Unit tests for the per-turn operational trace (no network, no live stack)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def trace_mod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reimport the module so env-derived module constants are re-read."""
    monkeypatch.setenv("PORTAL_TRACE", "1")
    monkeypatch.setenv("PORTAL_TRACE_BODIES", "0")
    monkeypatch.setenv("PORTAL_TRACE_MAX", "3")
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path / "traces"))
    import portal.platform.inference.router.trace as mod

    return importlib.reload(mod)


def _one_turn(mod, cid: str) -> None:
    mod.start_trace(cid)
    mod.note(workspace="auto-compliance", persona="cipanalyst")
    mod.span("route.resolved", to="auto-compliance", method="llm")
    mod.finalize_trace()


def test_record_round_trips(trace_mod) -> None:
    _one_turn(trace_mod, "p5-aaaa0001")
    record = trace_mod.read_trace("p5-aaaa0001")
    assert record is not None
    assert record["workspace"] == "auto-compliance"
    assert [s["name"] for s in record["spans"]] == ["route.resolved"]


def test_credentials_are_redacted(trace_mod) -> None:
    trace_mod.start_trace("p5-aaaa0002")
    trace_mod.note(authorization="Bearer sk-secret", api_key="sk-secret")
    trace_mod.span("backend.selected", token="sk-secret", model="granite4.1:30b")
    trace_mod.finalize_trace()
    record = trace_mod.read_trace("p5-aaaa0002")
    assert record["authorization"] == "<redacted>"
    assert record["api_key"] == "<redacted>"
    assert record["spans"][0]["token"] == "<redacted>"
    assert record["spans"][0]["model"] == "granite4.1:30b"


def test_finalize_overwrites_so_the_later_writer_wins(trace_mod) -> None:
    """The handler's finally writes first; the stream's finally must replace it."""
    trace = trace_mod.start_trace("p5-aaaa0003")
    trace_mod.finalize_trace()
    assert trace_mod.read_trace("p5-aaaa0003")["spans"] == []
    trace.span("tool.dispatch", tool="nerc_cip_requirement", outcome="ok")
    trace_mod.finalize_trace()
    assert len(trace_mod.read_trace("p5-aaaa0003")["spans"]) == 1


def test_ring_is_bounded(trace_mod) -> None:
    for index in range(6):
        _one_turn(trace_mod, f"p5-bbbb{index:04d}")
    assert len(trace_mod.recent_traces(50)) == 3
    assert trace_mod.read_trace("p5-bbbb0000") is None
    assert trace_mod.read_trace("p5-bbbb0005") is not None


def test_correlation_id_cannot_escape_the_directory(trace_mod) -> None:
    assert trace_mod.read_trace("../../etc/passwd") is None
    assert trace_mod.start_trace("../../etc/passwd") is None


def test_disabled_is_inert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTAL_TRACE", "0")
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path / "off"))
    import portal.platform.inference.router.trace as mod

    mod = importlib.reload(mod)
    assert mod.start_trace("p5-cccc0001") is None
    mod.span("route.resolved", to="auto")
    mod.note(workspace="auto")
    mod.finalize_trace()
    assert mod.recent_traces(10) == []


def test_bodies_are_opt_in_and_nested_credentials_are_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PORTAL_TRACE", "1")
    monkeypatch.setenv("PORTAL_TRACE_BODIES", "1")
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path / "bodies"))
    import portal.platform.inference.router.trace as mod

    mod = importlib.reload(mod)
    mod.start_trace("p5-dddd0001")
    mod.capture(messages=[{"role": "user", "content": "private prompt"}])
    mod.capture(
        backend_request={
            "messages": [
                {"role": "system", "content": "sealed prompt"},
                {"role": "user", "content": "private packet"},
            ],
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": True},
        }
    )
    mod.capture(tool_arguments={"lookup": {"api_key": "secret", "query": "CIP-007-6"}})
    mod.finalize_trace()

    record = mod.read_trace("p5-dddd0001")
    assert record["bodies_captured"] is True
    assert record["bodies"]["messages"][0]["content"] == "private prompt"
    assert record["bodies"]["backend_request"]["messages"][0]["head"] == "sealed prompt"
    assert record["bodies"]["backend_request"]["params"]["chat_template_kwargs"]["enable_thinking"]
    assert record["bodies"]["tool_arguments"]["lookup"]["api_key"] == "<redacted>"


def test_tool_loop_hops_keep_their_bodies_within_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every hop re-sends the whole conversation, so 20 hops of 4 KB tool results once
    outgrew the record cap and the cap dropped every body. Each hop now records only the
    messages new since the last one, with size and hash, and the record keeps them."""
    import hashlib

    monkeypatch.setenv("PORTAL_TRACE", "1")
    monkeypatch.setenv("PORTAL_TRACE_BODIES", "1")
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path / "hops"))
    import portal.platform.inference.router.trace as mod

    mod = importlib.reload(mod)
    mod.start_trace("p5-dddd0003")
    result = "R" * 4500
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
    ]
    for hop in range(20):
        mod.capture(backend_request={"model": "m", "messages": list(messages), "tools": [{}] * 46})
        messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{hop}"}]})
        messages.append({"role": "tool", "tool_call_id": f"c{hop}", "content": result})
    mod.finalize_trace()

    record = mod.read_trace("p5-dddd0003")
    assert not record.get("truncated")
    hops = record["bodies"]["backend_request"]
    assert len(hops) == 20
    assert [h["n_messages"] for h in hops] == [2 + 2 * n for n in range(20)]
    last = hops[19]["messages"]
    assert last[-1]["role"] == "tool" and last[-1]["chars"] == 4500
    assert last[-1]["sha256"] == hashlib.sha256(result.encode()).hexdigest()[:16]
    assert last[-1]["head_truncated"] is True and len(last[-1]["head"]) < 4500
    assert hops[19]["new_from"] == hops[18]["n_messages"]
    assert hops[0]["tools"] == 46


def test_oversized_bodies_are_dropped_with_a_marker_not_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PORTAL_TRACE", "1")
    monkeypatch.setenv("PORTAL_TRACE_BODIES", "1")
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path / "marker"))
    monkeypatch.setenv("PORTAL_TRACE_MAX_BYTES", "1024")
    import portal.platform.inference.router.trace as mod

    mod = importlib.reload(mod)
    mod.start_trace("p5-dddd0004")
    mod.capture(tool_arguments={"q": "x" * 5000})
    mod.finalize_trace()

    record = mod.read_trace("p5-dddd0004")
    assert record["truncated"] is True and record["bodies_dropped"] is True


def test_oversized_records_remain_bounded_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PORTAL_TRACE", "1")
    monkeypatch.setenv("PORTAL_TRACE_DIR", str(tmp_path / "bounded"))
    monkeypatch.setenv("PORTAL_TRACE_MAX_BYTES", "512")
    import portal.platform.inference.router.trace as mod

    mod = importlib.reload(mod)
    mod.start_trace("p5-dddd0002")
    mod.note(workspace="x" * 2000)
    mod.finalize_trace()

    path = tmp_path / "bounded" / "p5-dddd0002.json"
    assert path.stat().st_size <= 512
    record = mod.read_trace("p5-dddd0002")
    assert record["truncated"] is True
    assert record["correlation_id"] == "p5-dddd0002"


def test_helpers_never_raise_without_a_current_trace(trace_mod) -> None:
    trace_mod.span("orphan", detail="no turn in flight")
    trace_mod.note(workspace="none")
    trace_mod.finalize_trace()


def test_redaction_spares_token_counts_but_not_credentials():
    # wfe_math_20261018c: "<redacted>" token counts in /v1/trace crashed the WFE runner
    from portal.platform.inference.router.trace import redact

    out = redact(
        {
            "reasoning_tokens": 12,
            "answer_tokens": 30,
            "max_tokens": 512,
            "access_token": "s3cret",
            "x-token": "s3cret",
            "api_key": "k",
            "portal_timings": {"answer_tokens": 30, "authorization": "Bearer x"},
        }
    )
    assert out["reasoning_tokens"] == 12 and out["answer_tokens"] == 30 and out["max_tokens"] == 512
    assert out["access_token"] == out["x-token"] == out["api_key"] == "<redacted>"
    assert out["portal_timings"] == {"answer_tokens": 30, "authorization": "<redacted>"}
