"""Unit tests for the media cross-engine VRAM admission check (Slice 7,
TASK_VRAM_ADMISSION_V1). Mirrors the retired MLX-proxy admission tests (commit
91f13a9, tests/unit/test_mlx_proxy.py) for the analogous fit/too-large/
unknown-cost cases, adapted for the async `admit()` design and the media
model-size table.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from portal.modules.media.tools import _admission


class TestMediaModelMemoryDict:
    def test_dict_exists_and_nonempty(self):
        assert isinstance(_admission.MEDIA_MODEL_MEMORY_GB, dict)
        assert len(_admission.MEDIA_MODEL_MEMORY_GB) > 0

    def test_values_are_positive_floats(self):
        for key, gb in _admission.MEDIA_MODEL_MEMORY_GB.items():
            assert isinstance(gb, (int, float)), f"{key}: expected float, got {type(gb)}"
            assert gb > 0, f"{key}: memory estimate must be > 0 GB"

    def test_heavy_video_model_has_large_estimate(self):
        """The 14B video model that caused the live 2026-07-14 lockup must be >= 35GB."""
        assert _admission.MEDIA_MODEL_MEMORY_GB.get("video:wan21-nsfw", 0) >= 35.0

    def test_small_music_model_has_reasonable_estimate(self):
        assert _admission.MEDIA_MODEL_MEMORY_GB.get("music:small", 999) < 10.0

    def test_headroom_constant_exists(self):
        assert _admission.MEMORY_HEADROOM_GB >= 0


class TestEstimateJobGb:
    def test_known_model_returns_table_value(self):
        gb, known = _admission.estimate_job_gb("comfyui:sdxl")
        assert gb == _admission.MEDIA_MODEL_MEMORY_GB["comfyui:sdxl"]
        assert known is True

    def test_unknown_model_returns_conservative_default(self):
        gb, known = _admission.estimate_job_gb("comfyui:some-future-model")
        assert gb == _admission.MEMORY_UNKNOWN_DEFAULT_GB
        assert known is False


@pytest.mark.asyncio
class TestAdmit:
    async def test_admits_when_sufficient_memory(self):
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=64.0)):
            refusal = await _admission.admit("comfyui:sdxl")
        assert refusal is None

    async def test_refuses_when_insufficient_memory(self):
        # video:wan21-nsfw ~38.2GB + default 4GB headroom = 42.2GB needed; only 20GB free
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=20.0)):
            refusal = await _admission.admit("video:wan21-nsfw")
        assert refusal is not None
        assert refusal["success"] is False
        assert len(refusal["error"]) > 0

    async def test_refusal_message_is_actionable(self):
        """Refusal message must mention the model, a GB estimate, and recovery steps."""
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=10.0)):
            refusal = await _admission.admit("video:wan21-nsfw")
        assert refusal is not None
        msg = refusal["error"]
        assert "video:wan21-nsfw" in msg
        assert "GB" in msg
        assert any(word in msg.lower() for word in ["stop", "unload", "comfyui", "ollama"])

    async def test_unknown_model_admitted_when_memory_plentiful(self):
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=64.0)):
            refusal = await _admission.admit("comfyui:some-future-model")
        assert refusal is None

    async def test_unknown_model_refused_on_low_memory(self):
        # default estimate 16GB + 4GB headroom = 20GB needed; only 5GB free
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=5.0)):
            refusal = await _admission.admit("comfyui:some-future-model")
        assert refusal is not None

    async def test_borderline_passes(self):
        """Exactly at threshold should pass (<=, not <)."""
        gb = _admission.MEDIA_MODEL_MEMORY_GB["comfyui:sdxl"]
        exact = gb + _admission.MEMORY_HEADROOM_GB
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=exact)):
            refusal = await _admission.admit("comfyui:sdxl")
        assert refusal is None

    async def test_borderline_fails(self):
        gb = _admission.MEDIA_MODEL_MEMORY_GB["comfyui:sdxl"]
        just_short = gb + _admission.MEMORY_HEADROOM_GB - 0.1
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=just_short)):
            refusal = await _admission.admit("comfyui:sdxl")
        assert refusal is not None

    async def test_fails_open_when_memory_unmeasurable(self):
        """An unmeasurable free-memory signal must never block a job outright."""
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=None)):
            refusal = await _admission.admit("video:wan21-nsfw")
        assert refusal is None

    async def test_headroom_zero_disables_check(self):
        """MEDIA_MEMORY_HEADROOM_GB<=0 is the operator fail-open escape hatch."""
        with (
            patch.object(_admission, "MEMORY_HEADROOM_GB", 0),
            patch.object(_admission, "free_unified_gb", AsyncMock(return_value=0.0)),
        ):
            refusal = await _admission.admit("video:wan21-nsfw")
        assert refusal is None
