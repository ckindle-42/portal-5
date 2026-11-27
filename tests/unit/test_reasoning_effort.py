"""A4: reasoning_effort -> max_tokens cap, in both option injectors.

TASK_REASONING_OVERHAUL_REMAINING_V1 P1. Verifies the shared helper and its
wiring: an explicit reasoning_effort overrides a workspace's fixed predict_limit,
the key is always stripped from the outgoing body, and the two backends agree.
"""

import importlib

from portal.platform.inference.model_cards import card_thinking_level

val = importlib.import_module("portal.platform.inference.router.validation")

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


def test_card_thinking_level_uses_nearest_documented_token_limit():
    registry = {
        "qwen3.8": {"thinking_budget_levels": {"low": 4096, "medium": 16384, "xhigh": 49152}}
    }
    assert card_thinking_level("qwen3.8-test", 5000, registry) == "low"
    assert card_thinking_level("qwen3.8-test", 14000, registry) == "medium"
    assert card_thinking_level("qwen3.8-test", 4096, {"qwen3.8": {}}) is None


def test_wfe_runner_think_false_maps_to_reasoning_effort_none():
    # WFE-side parity (moved from tests/wfe/tests/test_wfe_contracts.py): only
    # reasoning_effort:"none" suppresses thinking on Ollama's /v1 surface.
    import tests.wfe.runner as rn

    assert rn._v1_think_fields("false") == {"think": False, "reasoning_effort": "none"}
    assert rn._v1_think_fields("true") == {"think": True}
    assert rn._v1_think_fields("default") == {}
