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


def test_helpers_never_raise_without_a_current_trace(trace_mod) -> None:
    trace_mod.span("orphan", detail="no turn in flight")
    trace_mod.note(workspace="none")
    trace_mod.finalize_trace()
