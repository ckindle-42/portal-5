"""A4: reasoning_effort -> max_tokens cap, in both option injectors.

TASK_REASONING_OVERHAUL_REMAINING_V1 P1. Verifies the shared helper and its
wiring: an explicit reasoning_effort overrides a workspace's fixed predict_limit,
the key is always stripped from the outgoing body, and the two backends agree.
"""

import importlib
from types import SimpleNamespace

import pytest

from portal.platform.inference.model_cards import card_thinking_level
from portal.platform.inference.ollama_native import to_native_request
from portal.platform.inference.router import streaming

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


def test_apply_helper_none_turns_thinking_off():
    body = {"reasoning_effort": "none", "messages": []}
    assert val._apply_reasoning_effort(body) is None
    assert body["think"] is False  # OpenAI "none" = no reasoning; must survive the strip
    assert "reasoning_effort" not in body and "max_tokens" not in body
    explicit = {"reasoning_effort": "none", "think": True, "messages": []}
    val._apply_reasoning_effort(explicit)
    assert explicit["think"] is True  # an explicit think wins


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


def test_card_thinking_level_uses_nearest_documented_token_limit():
    registry = {
        "qwen3.8": {"thinking_budget_levels": {"low": 4096, "medium": 16384, "xhigh": 49152}}
    }
    assert card_thinking_level("qwen3.8-test", 5000, registry) == "low"
    assert card_thinking_level("qwen3.8-test", 14000, registry) == "medium"
    assert card_thinking_level("qwen3.8-test", 4096, {"qwen3.8": {}}) is None


def test_omlx_injector_applies_workspace_budget_and_client_override(monkeypatch):
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"thinking_budget": 16384})
    default = val._inject_omlx_options({"messages": [], "stream": False}, "ws-test")
    client = val._inject_omlx_options(
        {"messages": [], "stream": False, "thinking_budget": 4096}, "ws-test"
    )
    assert default["thinking_budget"] == 16384
    assert client["thinking_budget"] == 4096


def test_ollama_injector_maps_client_budget_using_card_and_preserves_it_for_chain(monkeypatch):
    registry = {
        "qwen3.8": {"thinking_budget_levels": {"low": 4096, "medium": 16384, "xhigh": 49152}}
    }
    monkeypatch.setattr(
        val,
        "card_thinking_level",
        lambda tag, budget: card_thinking_level(tag, budget, registry),
    )
    monkeypatch.setitem(
        val.WORKSPACES,
        "ws-test",
        {"model_hint": "qwen3.8-test", "thinking_budget": 49152, "think": True},
    )
    request = {"model": "qwen3.8-test", "messages": [], "stream": False, "thinking_budget": 5000}
    out = val._inject_ollama_options(request, "ws-test")
    assert out["think"] == "low"
    assert out["thinking_budget"] == 5000
    assert request["thinking_budget"] == 5000


def test_ollama_ignores_budget_without_card_mapping_and_logs(monkeypatch, caplog):
    monkeypatch.setattr(val, "card_thinking_level", lambda _tag, _budget: None)
    monkeypatch.setitem(val.WORKSPACES, "ws-test", {"model_hint": "uncatalogued-model"})
    with caplog.at_level("DEBUG", logger=val.__name__):
        out = val._inject_ollama_options(
            {"model": "uncatalogued-model", "messages": [], "thinking_budget": 4096}, "ws-test"
        )
    native = to_native_request(out, can_think=True)
    assert "thinking_budget" not in native
    assert "Ignoring undocumented Ollama thinking_budget" in caplog.text


@pytest.mark.anyio
async def test_streaming_request_injects_workspace_budget(monkeypatch):
    workspace_id = "ws-budget-stream"
    monkeypatch.setitem(val.WORKSPACES, workspace_id, {"thinking_budget": 8192})
    monkeypatch.setattr(streaming, "_model_supports_tools", lambda _model: False)
    body, _, _, _ = await streaming._build_streaming_request(
        {"messages": [], "stream": True, "portal_no_tools": True},
        SimpleNamespace(type="omlx"),
        "omlx-model",
        workspace_id,
        "",
    )
    assert body["thinking_budget"] == 8192


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
