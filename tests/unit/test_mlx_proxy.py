"""Unit tests for model-size-aware admission control (P5-FUT-009).

Tests _check_memory_for_model() logic in isolation with mocked memory reads.
No MLX runtime required.
"""

from __future__ import annotations

import importlib.util
from unittest.mock import patch

import pytest


def _import_proxy():
    """Import mlx-proxy module. Handles hyphen in filename."""
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("mlx_proxy", Path("scripts/mlx-proxy.py"))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def proxy_module():
    return _import_proxy()


class TestModelMemoryDict:
    def test_model_memory_dict_exists(self, proxy_module):
        assert hasattr(proxy_module, "MODEL_MEMORY")
        assert isinstance(proxy_module.MODEL_MEMORY, dict)

    def test_model_memory_covers_all_known_models(self, proxy_module):
        """Every model in ALL_MODELS must appear in MODEL_MEMORY."""
        for model in proxy_module.ALL_MODELS:
            assert model in proxy_module.MODEL_MEMORY, (
                f"Model '{model}' listed in ALL_MODELS but missing from MODEL_MEMORY"
            )

    def test_memory_values_are_positive_floats(self, proxy_module):
        for model, gb in proxy_module.MODEL_MEMORY.items():
            assert isinstance(gb, (int, float)), f"{model}: expected float, got {type(gb)}"
            assert gb > 0, f"{model}: memory estimate must be > 0 GB"

    def test_heavy_model_has_large_estimate(self, proxy_module):
        """70B model must have > 35GB estimate."""
        heavy = "mlx-community/Llama-3.3-70B-Instruct-4bit"
        assert proxy_module.MODEL_MEMORY.get(heavy, 0) >= 35.0

    def test_small_model_has_reasonable_estimate(self, proxy_module):
        """3B model must have < 10GB estimate."""
        small = "mlx-community/Llama-3.2-3B-Instruct-8bit"
        assert proxy_module.MODEL_MEMORY.get(small, 999) < 10.0

    def test_headroom_constant_exists(self, proxy_module):
        assert hasattr(proxy_module, "MEMORY_HEADROOM_GB")
        assert proxy_module.MEMORY_HEADROOM_GB >= 8.0, "Headroom must be at least 8GB"


class TestCheckMemoryForModel:
    def test_ok_when_sufficient_memory(self, proxy_module):
        model = "mlx-community/Dolphin3.0-Llama3.1-8B-8bit"  # ~9GB
        # Simulate 64GB available — plenty
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=64.0):
            ok, msg = proxy_module._check_memory_for_model(model)
        assert ok is True
        assert msg == ""

    def test_rejected_when_insufficient_memory(self, proxy_module):
        model = "mlx-community/Qwen3-Coder-Next-4bit"  # ~46GB + 10GB headroom = 56GB
        # Only 20GB available
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=20.0):
            ok, msg = proxy_module._check_memory_for_model(model)
        assert ok is False
        assert len(msg) > 0
        assert "503" not in msg  # message is for logging; HTTP code set elsewhere

    def test_rejection_message_is_actionable(self, proxy_module):
        """Rejection message must mention the model, GB estimates, and recovery steps."""
        model = "mlx-community/Llama-3.3-70B-Instruct-4bit"  # ~40GB
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=10.0):
            ok, msg = proxy_module._check_memory_for_model(model)
        assert ok is False
        assert "40" in msg or "GB" in msg  # mentions size
        assert any(word in msg.lower() for word in ["stop", "unload", "free", "comfyui", "ollama"])

    def test_unknown_model_uses_conservative_default(self, proxy_module):
        """Unknown models use MEMORY_UNKNOWN_DEFAULT_GB, not 0 (not silently allowed)."""
        model = "some/unknown-model-xyz"
        # Available > default + headroom → ok
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=64.0):
            ok, msg = proxy_module._check_memory_for_model(model)
        assert ok is True

    def test_unknown_model_rejected_on_low_memory(self, proxy_module):
        model = "some/unknown-model-xyz"
        # Available = 5GB, default 20GB + 10GB headroom = 30GB required
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=5.0):
            ok, msg = proxy_module._check_memory_for_model(model)
        assert ok is False

    def test_borderline_passes(self, proxy_module):
        """Exactly at threshold should pass (>=, not >)."""
        model = "mlx-community/Dolphin3.0-Llama3.1-8B-8bit"  # 9GB
        headroom = proxy_module.MEMORY_HEADROOM_GB
        draft = proxy_module.DRAFT_MODEL_MAP.get(model, "")
        draft_mem = proxy_module.MODEL_MEMORY.get(draft, 0.5) if draft else 0.0
        exact = 9.0 + draft_mem + headroom
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=exact):
            ok, _ = proxy_module._check_memory_for_model(model)
        assert ok is True

    def test_borderline_fails(self, proxy_module):
        """Just below threshold should fail."""
        model = "mlx-community/Dolphin3.0-Llama3.1-8B-8bit"  # 9GB
        headroom = proxy_module.MEMORY_HEADROOM_GB
        draft = proxy_module.DRAFT_MODEL_MAP.get(model, "")
        draft_mem = proxy_module.MODEL_MEMORY.get(draft, 0.5) if draft else 0.0
        just_short = 9.0 + draft_mem + headroom - 0.1
        with patch.object(proxy_module, "_get_available_memory_gb", return_value=just_short):
            ok, _ = proxy_module._check_memory_for_model(model)
        assert ok is False


class TestBigModelMode:
    """Verify big-model mode constants and set (P5-BIG-001)."""

    def test_big_model_set_exists(self, proxy_module):
        assert hasattr(proxy_module, "BIG_MODEL_SET")
        assert isinstance(proxy_module.BIG_MODEL_SET, set)

    def test_qwen3_coder_next_is_in_big_model_set(self, proxy_module):
        """Qwen3-Coder-Next-4bit (46GB) must be in BIG_MODEL_SET."""
        assert "mlx-community/Qwen3-Coder-Next-4bit" in proxy_module.BIG_MODEL_SET

    def test_big_model_set_models_have_memory_entries(self, proxy_module):
        """Every model in BIG_MODEL_SET must have a MODEL_MEMORY entry."""
        for model in proxy_module.BIG_MODEL_SET:
            assert model in proxy_module.MODEL_MEMORY, (
                f"Big model '{model}' missing from MODEL_MEMORY"
            )

    def test_big_model_ctx_exists_and_is_reasonable(self, proxy_module):
        """BIG_MODEL_CTX must exist and be a reasonable context cap (4K–256K)."""
        assert hasattr(proxy_module, "BIG_MODEL_CTX")
        ctx = proxy_module.BIG_MODEL_CTX
        assert isinstance(ctx, int)
        assert 4096 <= ctx <= 262144, f"BIG_MODEL_CTX={ctx} out of expected range [4096, 262144]"

    def test_big_model_ctx_default_is_32k(self, proxy_module):
        """Default BIG_MODEL_CTX must be 32768 (suppresses KV cache spike at 46GB)."""
        import os

        if "MLX_BIG_MODEL_CTX" not in os.environ:
            assert proxy_module.BIG_MODEL_CTX == 32768, (
                f"Default BIG_MODEL_CTX should be 32768, got: {proxy_module.BIG_MODEL_CTX}"
            )

    def test_big_model_min_free_gb_exists(self, proxy_module):
        """BIG_MODEL_MIN_FREE_GB must exist and be > 0."""
        assert hasattr(proxy_module, "BIG_MODEL_MIN_FREE_GB")
        assert proxy_module.BIG_MODEL_MIN_FREE_GB > 0

    def test_big_model_min_free_gb_is_sane(self, proxy_module):
        """BIG_MODEL_MIN_FREE_GB must require at least a few GB free post-evict."""
        assert proxy_module.BIG_MODEL_MIN_FREE_GB >= 4.0, (
            f"BIG_MODEL_MIN_FREE_GB={proxy_module.BIG_MODEL_MIN_FREE_GB} is too low — "
            "need at least 4GB free after eviction to avoid OOM"
        )

    def test_big_model_active_flag_exists(self, proxy_module):
        """_big_model_active module-level flag must be defined."""
        assert hasattr(proxy_module, "_big_model_active")
        assert isinstance(proxy_module._big_model_active, bool)

    def test_devstral_2507_not_in_big_model_set(self, proxy_module):
        """Devstral-Small-2507-MLX-4bit (~15GB) must NOT be in BIG_MODEL_SET — it fits normally."""
        assert "lmstudio-community/Devstral-Small-2507-MLX-4bit" not in proxy_module.BIG_MODEL_SET
