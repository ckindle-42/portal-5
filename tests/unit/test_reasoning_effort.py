"""A4: reasoning_effort -> max_tokens cap, in both option injectors.

TASK_REASONING_OVERHAUL_REMAINING_V1 P1. Verifies the shared helper and its
wiring: an explicit reasoning_effort overrides a workspace's fixed predict_limit,
the key is always stripped from the outgoing body, and the two backends agree.
"""

import importlib

import pytest

val = importlib.import_module("portal.platform.inference.router.validation")

LOW = val._REASONING_EFFORT_PREDICT["low"]
MED = val._REASONING_EFFORT_PREDICT["medium"]
HIGH = val._REASONING_EFFORT_PREDICT["high"]


def test_apply_helper_maps_and_strips():
    body = {"reasoning_effort": "high", "messages": []}
    out = val._apply_reasoning_effort(body)
    assert out == (HIGH, "high")
    assert body["max_tokens"] == HIGH
    assert "reasoning_effort" not in body  # always stripped


def test_apply_helper_unknown_is_noop_but_strips():
    body = {"reasoning_effort": "ludicrous", "messages": []}
    assert val._apply_reasoning_effort(body) is None
    assert "max_tokens" not in body
    assert "reasoning_effort" not in body  # still stripped so backend never sees it


def test_apply_helper_absent_is_noop():
    body = {"messages": []}
    assert val._apply_reasoning_effort(body) is None


@pytest.mark.parametrize("effort,expected", [("low", LOW), ("medium", MED), ("high", HIGH)])
def test_ollama_injector_effort_overrides_predict_limit(monkeypatch, effort, expected):
    # workspace declares a fixed predict_limit; effort must win.
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"predict_limit": 1234})
    body = {"reasoning_effort": effort, "messages": [], "stream": False}
    out = val._inject_ollama_options(body, "ws-test")
    assert out["max_tokens"] == expected
    assert "reasoning_effort" not in out


@pytest.mark.parametrize("effort,expected", [("low", LOW), ("medium", MED), ("high", HIGH)])
def test_omlx_injector_effort_overrides_and_hints(monkeypatch, effort, expected):
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"predict_limit": 1234})
    body = {"reasoning_effort": effort, "messages": [], "stream": False}
    out = val._inject_omlx_options(body, "ws-test")
    assert out["max_tokens"] == expected
    assert out["chat_template_kwargs"]["reasoning_effort"] == effort
    assert "reasoning_effort" not in out


def test_no_effort_falls_back_to_predict_limit(monkeypatch):
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"predict_limit": 1234})
    for inj in (val._inject_ollama_options, val._inject_omlx_options):
        out = inj({"messages": [], "stream": False}, "ws-test")
        assert out["max_tokens"] == 1234  # workspace default when no effort given


# ── think:false must reach the backend in the form /v1 actually honours ──────
# Regression guard for the 2026-09-12 finding: Ollama 0.33.2's OpenAI-compat
# endpoint silently drops a top-level `think`, so every `think: false` workspace
# was reasoning anyway. `reasoning_effort: "none"` is the form it honours.


def test_think_false_emits_reasoning_effort_none(monkeypatch):
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"think": False})
    out = val._inject_ollama_options({"messages": [], "stream": False}, "ws-test")
    assert out["reasoning_effort"] == "none"
    assert out["think"] is False  # native knob still sent for any /api/chat path


def test_think_true_emits_no_reasoning_effort(monkeypatch):
    # Any tier but "none" is rejected 400 by a model without the thinking
    # capability, and thinking is the template default anyway — so inject none.
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"think": True})
    out = val._inject_ollama_options({"messages": [], "stream": False}, "ws-test")
    assert "reasoning_effort" not in out
    assert out["think"] is True


def test_think_unset_emits_neither_key(monkeypatch):
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"predict_limit": 1234})
    out = val._inject_ollama_options({"messages": [], "stream": False}, "ws-test")
    assert "reasoning_effort" not in out
    assert "think" not in out


def test_think_false_suppression_survives_caller_effort(monkeypatch):
    """A caller's reasoning_effort is a token-budget tier, popped upstream. It
    must set the cap AND still leave the workspace's suppression on the wire."""
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"think": False, "predict_limit": 1234})
    out = val._inject_ollama_options(
        {"reasoning_effort": "high", "messages": [], "stream": False}, "ws-test"
    )
    assert out["max_tokens"] == HIGH  # caller's budget override still wins
    assert out["reasoning_effort"] == "none"  # ...and thinking stays suppressed
