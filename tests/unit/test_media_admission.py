"""Unit tests for the media cross-engine VRAM admission check (Slice 7,
TASK_VRAM_ADMISSION_V1). Mirrors the retired MLX-proxy admission tests (commit
91f13a9, tests/unit/test_mlx_proxy.py) for the analogous fit/too-large/
unknown-cost cases, adapted for the async `admit()` design and the media
model-size table.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from portal.modules.media.tools import _admission

REPO = Path(__file__).resolve().parents[2]


def test_no_comfyui_residue_in_launch_scripts():
    """The ComfyUI image/video subsystem was removed (TASK_IMAGE_VIDEO_OVERHAUL_V1)."""
    for rel in ("launch.sh", "scripts/lib/services.sh", "scripts/lib/util.sh"):
        assert "comfyui" not in (REPO / rel).read_text().lower(), rel


def test_mflux_installer_is_apple_silicon_only():
    services = (REPO / "scripts/lib/services.sh").read_text()
    installer = services.split("_launch_install_mflux()", 1)[1].split("\n}", 1)[0]
    assert 'ARCH" != "arm64"' in installer
    assert "mflux-generate" in installer


def test_routine_rebuilds_do_not_reference_removed_video_service():
    launch = (REPO / "launch.sh").read_text()
    assert "mcp-video" not in launch
    assert "mcp-comfyui" not in launch


class TestMediaModelMemoryDict:
    def test_dict_exists_and_nonempty(self):
        assert isinstance(_admission.MEDIA_MODEL_MEMORY_GB, dict)
        assert len(_admission.MEDIA_MODEL_MEMORY_GB) > 0

    def test_values_are_positive_floats(self):
        for key, gb in _admission.MEDIA_MODEL_MEMORY_GB.items():
            assert isinstance(gb, (int, float)), f"{key}: expected float, got {type(gb)}"
            assert gb > 0, f"{key}: memory estimate must be > 0 GB"

    def test_video_model_has_large_estimate(self):
        """LTX-2.3 video packs run a large working set — keep the estimate conservative."""
        assert _admission.MEDIA_MODEL_MEMORY_GB.get("video_mlx:ltx-2.3-q8", 0) >= 25.0

    def test_music_models_use_live_complete_quality_estimates(self):
        # Raw sampled peak working set — admit() adds MEMORY_HEADROOM_GB on top,
        # like every other entry. minimax3 was 27.0 (4GB headroom double-counted).
        assert _admission.MEDIA_MODEL_MEMORY_GB["music:minimax3"] == 22.0
        assert _admission.MEDIA_MODEL_MEMORY_GB["music:acestep-sft"] == 40.0

    def test_headroom_constant_exists(self):
        assert _admission.MEMORY_HEADROOM_GB >= 0

    def test_mflux_image_models_use_measured_estimates(self):
        assert _admission.MEDIA_MODEL_MEMORY_GB["mflux:schnell"] == 15.0
        assert _admission.MEDIA_MODEL_MEMORY_GB["mflux:klein"] == 18.0


class TestEstimateJobGb:
    def test_known_model_returns_table_value(self):
        gb, known = _admission.estimate_job_gb("mflux:schnell")
        assert gb == _admission.MEDIA_MODEL_MEMORY_GB["mflux:schnell"]
        assert known is True

    def test_unknown_model_returns_conservative_default(self):
        gb, known = _admission.estimate_job_gb("mflux:some-future-model")
        assert gb == _admission.MEMORY_UNKNOWN_DEFAULT_GB
        assert known is False


@pytest.mark.asyncio
class TestAdmit:
    async def test_admits_when_sufficient_memory(self):
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=64.0)):
            refusal = await _admission.admit("mflux:schnell")
        assert refusal is None

    async def test_refuses_when_insufficient_memory(self):
        # video_mlx:ltx-2.3-q8 ~34GB + default 4GB headroom = 38GB needed; only 20GB free
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=20.0)):
            refusal = await _admission.admit("video_mlx:ltx-2.3-q8")
        assert refusal is not None
        assert refusal["success"] is False
        assert len(refusal["error"]) > 0

    async def test_refusal_message_is_actionable(self):
        """User-facing error states the shortfall and that it's temporary; the
        operator_hint carries the unload/wait recovery guidance."""
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=10.0)):
            refusal = await _admission.admit("video_mlx:ltx-2.3-q8")
        assert refusal is not None
        assert refusal["retryable"] is True
        msg = refusal["error"]
        assert "GB" in msg
        assert "10.0GB" in msg  # the measured free amount
        assert "temporary" in msg.lower()
        hint = refusal["operator_hint"]
        assert any(word in hint.lower() for word in ["stop", "unload", "wait", "ollama"])

    async def test_unknown_model_admitted_when_memory_plentiful(self):
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=64.0)):
            refusal = await _admission.admit("mflux:some-future-model")
        assert refusal is None

    async def test_unknown_model_refused_on_low_memory(self):
        # default estimate 16GB + 4GB headroom = 20GB needed; only 5GB free
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=5.0)):
            refusal = await _admission.admit("mflux:some-future-model")
        assert refusal is not None

    async def test_borderline_passes(self):
        """Exactly at threshold should pass (<=, not <)."""
        gb = _admission.MEDIA_MODEL_MEMORY_GB["mflux:schnell"]
        exact = gb + _admission.MEMORY_HEADROOM_GB
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=exact)):
            refusal = await _admission.admit("mflux:schnell")
        assert refusal is None

    async def test_borderline_fails(self):
        gb = _admission.MEDIA_MODEL_MEMORY_GB["mflux:schnell"]
        just_short = gb + _admission.MEMORY_HEADROOM_GB - 0.1
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=just_short)):
            refusal = await _admission.admit("mflux:schnell")
        assert refusal is not None

    async def test_fails_open_when_memory_unmeasurable(self):
        """An unmeasurable free-memory signal must never block a job outright."""
        with patch.object(_admission, "free_unified_gb", AsyncMock(return_value=None)):
            refusal = await _admission.admit("video_mlx:ltx-2.3-q8")
        assert refusal is None

    async def test_headroom_zero_disables_check(self):
        """MEDIA_MEMORY_HEADROOM_GB<=0 is the operator fail-open escape hatch."""
        with (
            patch.object(_admission, "MEMORY_HEADROOM_GB", 0),
            patch.object(_admission, "free_unified_gb", AsyncMock(return_value=0.0)),
        ):
            refusal = await _admission.admit("video_mlx:ltx-2.3-q8")
        assert refusal is None


class TestFreeGbFromVmStat:
    """Regression for false admission refusals: (1) ACE-Step (~40GB) was refused
    with 35.6GB reported free while a psutil system_stats reading showed 44GB —
    fixed by adding inactive pages. (2) MiniMax (~27GB) was refused with ~29GB
    free+inactive while memory_pressure reported ~41GB available with the Docker
    Desktop VM running — fixed by also counting speculative (read-ahead file
    cache) and purgeable pages, both reclaimed as fast as free pages."""

    _VM_STAT_OUT = (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free:                                  2330580.\n"
        "Pages active:                                 472285.\n"
        "Pages inactive:                               562220.\n"
        "Pages speculative:                             120000.\n"
        "Pages purgeable:                                 3000.\n"
    )

    def test_counts_free_inactive_speculative_purgeable(self):
        with patch("subprocess.check_output", return_value=self._VM_STAT_OUT.encode()):
            free_gb = _admission._free_gb_from_vm_stat()
        assert free_gb is not None
        pages = 2330580 + 562220 + 120000 + 3000
        assert free_gb == pytest.approx(pages * 16384 / 1024**3, abs=0.01)

    def test_missing_speculative_and_purgeable_default_to_zero(self):
        out = (
            "Pages free:                                  2330580.\n"
            "Pages inactive:                               562220.\n"
        )
        with patch("subprocess.check_output", return_value=out.encode()):
            free_gb = _admission._free_gb_from_vm_stat()
        assert free_gb == pytest.approx((2330580 + 562220) * 16384 / 1024**3, abs=0.01)

    def test_returns_none_when_inactive_missing(self):
        out = "Pages free:                                  2330580.\n"
        with patch("subprocess.check_output", return_value=out.encode()):
            assert _admission._free_gb_from_vm_stat() is None


class TestMediaModelMemoryDictInSyncWithWikiFact:
    """_admission.py's docstring explains MEDIA_MODEL_MEMORY_GB is deliberately
    NOT imported from seed_facts.py (Rule 3: MCP modules stay independent) but
    kept as a manually-synced copy instead. Regression test for drift going
    uncaught."""

    def test_tables_match(self):
        import portal.platform.wiki.adapters.seed_facts as seed_facts

        assert seed_facts.MEDIA_MODEL_MEMORY_GB == _admission.MEDIA_MODEL_MEMORY_GB, (
            "portal/modules/media/tools/_admission.py's MEDIA_MODEL_MEMORY_GB "
            "has drifted from portal/platform/wiki/adapters/seed_facts.py's copy "
            "— update both together."
        )
