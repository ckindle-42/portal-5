"""Unit tests for the media cross-engine VRAM admission check (Slice 7,
TASK_VRAM_ADMISSION_V1). Mirrors the retired MLX-proxy admission tests (commit
91f13a9, tests/unit/test_mlx_proxy.py) for the analogous fit/too-large/
unknown-cost cases, adapted for the async `admit()` design and the media
model-size table.
"""

from __future__ import annotations

from portal.modules.media.tools import _admission


class TestMediaModelMemoryDict:
    def test_dict_exists_and_nonempty(self):
        assert isinstance(_admission.MEDIA_MODEL_MEMORY_GB, dict)
        assert len(_admission.MEDIA_MODEL_MEMORY_GB) > 0

    def test_values_are_positive_floats(self):
        for key, gb in _admission.MEDIA_MODEL_MEMORY_GB.items():
            assert isinstance(gb, (int, float)), f"{key}: expected float, got {type(gb)}"
            assert gb > 0, f"{key}: memory estimate must be > 0 GB"

    def test_video_model_has_large_estimate(self):
        """LTX-2.5 measured 15.8GiB peak — the estimate must stay above it."""
        assert _admission.MEDIA_MODEL_MEMORY_GB.get("video_mlx:ltx-2.5-q4", 0) >= 17.0

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
