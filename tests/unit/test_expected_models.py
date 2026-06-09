"""Unit tests for the expected-model resolution helper."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from expected_models import (
    expected_model_keys,
    expected_model_keys_for_persona,
    is_mlx_model,
    model_matches_expected,
    resolve_expected,
)


def test_mlx_model_detected_by_org_prefix():
    assert is_mlx_model("mlx-community/Qwen3-Coder-Next-4bit") is True
    assert is_mlx_model("Jackrong/MLX-Qwopus3.5-27B-v3-8bit") is True
    assert is_mlx_model("dolphin-llama3:8b") is False
    assert is_mlx_model("") is False


def test_unknown_workspace_returns_empty():
    keys, src = expected_model_keys("auto-nonexistent")
    assert keys == []
    assert "unknown" in src.lower()


def test_match_substring_case_insensitive():
    keys = ["qwen3-coder-next-4bit", "qwen3-coder"]
    assert model_matches_expected(
        "mlx-community/Qwen3-Coder-Next-4bit", keys
    ) is True
    assert model_matches_expected("qwen3-coder:30b", keys) is True
    assert model_matches_expected("dolphin-llama3:8b", keys) is False
    assert model_matches_expected("", keys) is False
    assert model_matches_expected("qwen3-coder:30b", []) is False


def test_persona_resolves_via_workspace():
    keys, src = expected_model_keys_for_persona("bugdiscoverycodeassistant")
    assert keys, f"expected resolution, got {keys} ({src})"
    assert "via workspace 'auto-coding'" in src


def test_unknown_persona_returns_empty():
    keys, src = expected_model_keys_for_persona("nonexistentpersona")
    assert keys == []
    assert "not in" in src.lower()


def test_resolve_expected_dispatches():
    keys, _ = resolve_expected(workspace_id="auto-security")
    assert keys
    keys2, _ = resolve_expected(persona_slug="cybersecurityspecialist")
    assert keys2
    keys3, src = resolve_expected()
    assert keys3 == []
