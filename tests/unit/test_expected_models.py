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


def test_workspace_with_both_hints_returns_mlx_first_when_ready():
    keys, src = expected_model_keys("auto-coding", mlx_state="ready")
    assert keys, f"expected at least one key, got {keys} ({src})"
    assert keys[0].startswith("glm"), f"MLX preferred when ready, got {keys}"
    assert any("qwen3-coder" in k for k in keys)


def test_workspace_with_mlx_down_returns_ollama_only():
    keys, src = expected_model_keys("auto-coding", mlx_state="down")
    assert keys, f"expected Ollama hint, got {keys} ({src})"
    assert not any("glm" in k for k in keys), \
        f"MLX hint must be excluded when down, got {keys}"
    assert any("qwen3-coder" in k for k in keys)


def test_ollama_only_workspace_unaffected_by_mlx_state():
    # auto-blueteam has no mlx_model_hint, so MLX state should not change results
    keys_ready, _ = expected_model_keys("auto-blueteam", mlx_state="ready")
    keys_down, _ = expected_model_keys("auto-blueteam", mlx_state="down")
    assert keys_ready == keys_down


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
