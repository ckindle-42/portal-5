"""The reading seat's Qwen3.8 A/B arm: addressable, harness-constant, window-bounded.

One test for BRIEF_READING_SEAT_AB_20261127: the candidate arm must be drivable
by the acceptance harness without moving the production seat, hold the reading
seat's prompt/tools/answer budget byte-for-byte, and declare the window its tag
actually bakes (the finding that bounds the live run).
"""

from __future__ import annotations

import yaml

from portal.modules.compliance.core.dual_document import PERSONA_TOOLS_RESERVE_TOKENS
from portal.platform.inference.config import effective_workspace

#: The CIP-007-6 R2 dual-document payload, MEASURED at DD4's pipeline turn on
#: oMLX (dual_document.py): 86,969 real prompt tokens for a payload the 3.17
#: floor prices at 91,944.
R2_PAYLOAD_PROMPT_TOKENS = 86_969


def _seat(seat: str) -> dict:
    portal = yaml.safe_load(open("config/portal.yaml", encoding="utf-8"))
    return effective_workspace(portal["workspaces"], seat)


def test_reading_qwen38_arm_is_addressable_harness_constant_and_window_bounded() -> None:
    from scripts.compliance_acceptance import config_workspace_for_seat, workspace_for_seat

    incumbent = _seat("auto-compliance::reading")
    candidate = _seat("auto-compliance::reading-qwen38")

    # Addressable: the harness drives the variant, the incumbent keeps its alias.
    assert workspace_for_seat("auto-compliance::reading-qwen38") == (
        "auto-compliance::reading-qwen38"
    )
    assert workspace_for_seat(incumbent["model_hint"]) == "compliance-reading"
    assert config_workspace_for_seat(incumbent["model_hint"]) == "auto-compliance::reading"
    assert config_workspace_for_seat("auto-compliance::reading-qwen38") == (
        "auto-compliance::reading-qwen38"
    )
    assert incumbent["model_hint"] != candidate["model_hint"]

    # Harness constant: prompt, OWUI prompt, tools, hop-1 tool_choice, answer budget.
    assert candidate["system_prompt_append"] == incumbent["system_prompt_append"]
    assert candidate["owui_system_prompt"] == incumbent["owui_system_prompt"]
    assert candidate["tools"] == incumbent["tools"]
    assert candidate["tool_choice"] == incumbent["tool_choice"] == "required"
    assert candidate["predict_limit"] == incumbent["predict_limit"]
    assert candidate["think"] is False and candidate["emits_reasoning"] is False

    # Sampling is the Qwen3.8-27B card's instruct row (tier 1 — build provider).
    card = yaml.safe_load(open("config/model_card_expectations.yaml", encoding="utf-8"))
    instruct = card["models"]["qwen3.8"]["recommended_sampling_modes"]["instruct"]
    for key, want in instruct.items():
        assert candidate[key] == want, key

    # Window: the declared limit is the ctx96k tag's baked window, and the
    # payload budget it leaves is below the measured R2 payload — the arm cannot
    # hold the seat's real dual-document read whole (the report's finding).
    assert candidate["context_limit"] == 98_304
    budget = candidate["context_limit"] - candidate["predict_limit"] - PERSONA_TOOLS_RESERVE_TOKENS
    assert budget < R2_PAYLOAD_PROMPT_TOKENS
