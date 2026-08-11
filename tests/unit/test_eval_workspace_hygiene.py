"""Unit coverage for BW (eval-workspace config hygiene), TASK-BENCH-FOLLOWUP-001 Part 3.

Guards against the two footguns that cost three benching passes on Deepwen:
context_limit silently dropped without a baked -ctxNk tag (P5-OLLAMA-OPTIONS-001),
and tool_choice: required inherited from a cloned workspace without re-verification.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validation import personas


def _patch_portal_yaml(monkeypatch, workspaces: dict) -> None:
    payload = yaml.dump({"workspaces": workspaces})
    orig_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self.name == "portal.yaml":
            return payload
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)


def test_passes_on_clean_workspaces(monkeypatch):
    _patch_portal_yaml(
        monkeypatch,
        {
            "bench-clean": {
                "module": "eval",
                "model_hint": "some-model:q4-ctx16k",
                "ctx_validated": True,
                "tool_choice": "required",
                "tool_choice_verified": True,
            },
            "bench-no-ctx-suffix-no-limit": {
                "module": "eval",
                "model_hint": "some-model:q4",
            },
            "auto-general": {
                "module": "general",
                "model_hint": "some-model:q4",
                "context_limit": 8192,
            },
        },
    )
    status, detail, _ = personas.check_eval_workspace_config_hygiene()
    assert status == "PASS", detail


def test_flags_dropped_context_limit(monkeypatch):
    _patch_portal_yaml(
        monkeypatch,
        {
            "bench-dropped": {
                "module": "eval",
                "model_hint": "some-model:q4",
                "context_limit": 8192,
            },
        },
    )
    status, detail, _ = personas.check_eval_workspace_config_hygiene()
    assert status == "FAIL"
    assert "bench-dropped" in detail
    assert "P5-OLLAMA-OPTIONS-001" in detail


def test_flags_unvalidated_baked_ctx(monkeypatch):
    _patch_portal_yaml(
        monkeypatch,
        {
            "bench-copied": {
                "module": "eval",
                "model_hint": "some-model:q4-ctx32k",
            },
        },
    )
    status, detail, _ = personas.check_eval_workspace_config_hygiene()
    assert status == "FAIL"
    assert "bench-copied" in detail
    assert "ctx_validated" in detail


def test_flags_unverified_tool_choice(monkeypatch):
    _patch_portal_yaml(
        monkeypatch,
        {
            "bench-forced": {
                "module": "eval",
                "model_hint": "some-model:q4-ctx16k",
                "ctx_validated": True,
                "tool_choice": "required",
            },
        },
    )
    status, detail, _ = personas.check_eval_workspace_config_hygiene()
    assert status == "FAIL"
    assert "bench-forced" in detail
    assert "tool_choice_verified" in detail


def test_grandfathered_workspaces_exempt_from_ctx_validation(monkeypatch):
    workspaces = {
        wid: {"module": "eval", "model_hint": "some-model:q4-ctx8k"}
        for wid in personas._CTX_HYGIENE_GRANDFATHERED
    }
    _patch_portal_yaml(monkeypatch, workspaces)
    status, detail, _ = personas.check_eval_workspace_config_hygiene()
    assert status == "PASS", detail
