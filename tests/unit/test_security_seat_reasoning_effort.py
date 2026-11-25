"""Per-seat ``reasoning_effort`` key: the Inkling security seats serve what was benchmarked.

The 2026-11-24 QAT security benchmark ran the oMLX Inkling seat at
``reasoning_effort: low`` (8/8), but the production seats set nothing, so the Inkling
template served its default effort (high) — a configuration that was never measured.
The Inkling template has no ``enable_thinking`` switch, so ``think`` cannot express it;
the seat key is injected for oMLX as ``chat_template_kwargs.reasoning_effort``.
"""

from __future__ import annotations

import importlib

val = importlib.import_module("portal.platform.inference.router.validation")


def test_seat_effort_reaches_omlx_template_kwargs(monkeypatch) -> None:
    monkeypatch.setitem(val.WORKSPACES, "ws-inkling", {"reasoning_effort": "low"})
    out = val._inject_omlx_options({"messages": [], "stream": True}, "ws-inkling")
    assert out["chat_template_kwargs"]["reasoning_effort"] == "low"
    # The seat key configures reasoning depth only — the output budget is untouched.
    assert out["max_tokens"] == val._DEFAULT_PREDICT_LIMIT


def test_seat_effort_respects_seat_predict_limit(monkeypatch) -> None:
    monkeypatch.setitem(
        val.WORKSPACES, "ws-inkling", {"reasoning_effort": "low", "predict_limit": 4096}
    )
    out = val._inject_omlx_options({"messages": [], "stream": True}, "ws-inkling")
    assert out["chat_template_kwargs"]["reasoning_effort"] == "low"
    assert out["max_tokens"] == 4096


def test_caller_template_kwargs_win_over_seat_effort(monkeypatch) -> None:
    monkeypatch.setitem(val.WORKSPACES, "ws-inkling", {"reasoning_effort": "low"})
    body = {"messages": [], "chat_template_kwargs": {"reasoning_effort": "high"}}
    out = val._inject_omlx_options(body, "ws-inkling")
    assert out["chat_template_kwargs"]["reasoning_effort"] == "high"


def test_inbound_request_effort_wins_and_still_caps(monkeypatch) -> None:
    monkeypatch.setitem(val.WORKSPACES, "ws-inkling", {"reasoning_effort": "low"})
    body = {"messages": [], "reasoning_effort": "medium", "stream": True}
    out = val._inject_omlx_options(body, "ws-inkling")
    assert out["chat_template_kwargs"]["reasoning_effort"] == "medium"
    assert out["max_tokens"] == val._REASONING_EFFORT_PREDICT["medium"]


def test_workspaces_without_the_key_are_unchanged(monkeypatch) -> None:
    monkeypatch.setitem(val.WORKSPACES, "ws-plain", {"predict_limit": 512})
    out = val._inject_omlx_options({"messages": [], "stream": True}, "ws-plain")
    assert "chat_template_kwargs" not in out


def test_think_still_maps_to_enable_thinking_alongside_seat_effort(monkeypatch) -> None:
    monkeypatch.setitem(val.WORKSPACES, "ws-mixed", {"reasoning_effort": "low", "think": False})
    out = val._inject_omlx_options({"messages": [], "stream": True}, "ws-mixed")
    assert out["chat_template_kwargs"]["enable_thinking"] is False
    assert out["chat_template_kwargs"]["reasoning_effort"] == "low"


def test_options_note_records_the_served_effort(monkeypatch) -> None:
    """The receipt reads the template kwarg — the top-level key is always popped."""
    from portal.platform.inference.router import trace as trace_mod

    captured: dict = {}
    monkeypatch.setattr(trace_mod, "note", lambda **fields: captured.update(fields))
    monkeypatch.setitem(val.WORKSPACES, "ws-inkling", {"reasoning_effort": "low"})
    val._inject_omlx_options({"messages": [], "stream": True}, "ws-inkling")
    assert captured["options_applied"]["reasoning_effort"] == "low"


def test_security_seats_declare_the_benchmarked_effort() -> None:
    """auto-security and both abliterated variants carry effort low, from the YAML."""
    from portal.platform.inference.config import effective_workspace, load_portal_config

    config = load_portal_config()
    assert config.workspaces["auto-security"].reasoning_effort == "low"
    for variant in ("uncensored", "purpleteam-deep"):
        merged = effective_workspace(config.workspaces, f"auto-security::{variant}")
        assert merged["reasoning_effort"] == "low", variant
        assert merged.get("think") is None, f"{variant}: knob is effort, not think"
