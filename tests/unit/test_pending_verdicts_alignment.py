"""alignment_analysis()'s runtime-capability gate (TASK-DECISION-GATE-001)."""

from __future__ import annotations

import scripts.pending_verdicts_report as pvr

CLAIMS_YES_TOOLS = {
    "description": "some card",
    "capabilities": {},
    "deployment_notes": ["advertises tool-use / function-calling"],
}

CLAIMS_REASONING = {
    "description": "some card",
    "capabilities": {},
    "deployment_notes": ["reasoning-trace capability"],
}

SLOT_NO_TOOLS = [{"workspace": "bench-x", "description": "x", "name": "x", "tools": []}]
SLOT_NO_REASONING = [
    {"workspace": "bench-x", "description": "x", "name": "x", "tools": [], "emits_reasoning": False}
]


def test_tool_mismatch_suppressed_when_runtime_has_no_tools(monkeypatch):
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: ["completion"])
    result = pvr.alignment_analysis(CLAIMS_YES_TOOLS, SLOT_NO_TOOLS, tag="dolphin-llama3:8b")
    assert not any("has no tools" in m for m in result["mismatches"])
    assert any("false-flag resolved" in m for m in result["matches"])


def test_tool_mismatch_flagged_when_runtime_confirms_tools(monkeypatch):
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: ["completion", "tools"])
    result = pvr.alignment_analysis(CLAIMS_YES_TOOLS, SLOT_NO_TOOLS, tag="some-model:latest")
    assert any("has no tools" in m for m in result["mismatches"])


def test_tool_mismatch_flagged_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: None)
    result = pvr.alignment_analysis(CLAIMS_YES_TOOLS, SLOT_NO_TOOLS, tag="some-model:latest")
    assert any("has no tools" in m for m in result["mismatches"])


def test_reasoning_mismatch_suppressed_when_runtime_has_no_thinking(monkeypatch):
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: ["completion"])
    result = pvr.alignment_analysis(
        CLAIMS_REASONING,
        SLOT_NO_REASONING,
        tag="hf.co/Andycurrent/Mistral-7B-Uncensored-GGUF:Q4_K_M",
    )
    assert not any("no slot has" in m for m in result["mismatches"])
    assert any("false-flag resolved" in m for m in result["matches"])


def test_reasoning_mismatch_flagged_when_runtime_confirms_thinking(monkeypatch):
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: ["completion", "thinking"])
    result = pvr.alignment_analysis(CLAIMS_REASONING, SLOT_NO_REASONING, tag="some-model:latest")
    assert any("no slot has" in m for m in result["mismatches"])


def test_reasoning_mismatch_flagged_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: None)
    result = pvr.alignment_analysis(CLAIMS_REASONING, SLOT_NO_REASONING, tag="some-model:latest")
    assert any("no slot has" in m for m in result["mismatches"])


def test_reasoning_explicit_category_demoted_when_runtime_has_no_thinking(monkeypatch):
    reasoning_cat = next(c for c in pvr.CAPABILITY_CATEGORIES if c["id"] == "reasoning-explicit")
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: ["completion"])
    demoted, note = pvr._reconcile_category_with_runtime(
        reasoning_cat, {"tag": "some-model:latest"}
    )
    assert demoted["id"] != "reasoning-explicit"
    assert note and "no `thinking` capability" in note


def test_reasoning_explicit_category_confirmed_when_runtime_has_thinking(monkeypatch):
    reasoning_cat = next(c for c in pvr.CAPABILITY_CATEGORIES if c["id"] == "reasoning-explicit")
    monkeypatch.setattr(pvr, "_ollama_capabilities", lambda tag: ["completion", "thinking"])
    kept, note = pvr._reconcile_category_with_runtime(reasoning_cat, {"tag": "some-model:latest"})
    assert kept["id"] == "reasoning-explicit"
    assert note is None
