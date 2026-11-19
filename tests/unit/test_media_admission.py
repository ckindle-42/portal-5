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

    def test_video_models_use_bucketed_estimates(self):
        """LTX memory scales with resolution: the measured 512x320 anchor stays
        above its 15.8GiB footprint, the 704x480 bucket is the conservative
        estimate, and the Wan2.2-5B fallback carries its own key."""
        assert _admission.MEDIA_MODEL_MEMORY_GB["video_mlx:ltx-2.5-q4"] >= 17.0
        assert _admission.MEDIA_MODEL_MEMORY_GB["video_mlx:ltx-2.5-q4-512"] >= 17.0
        assert _admission.MEDIA_MODEL_MEMORY_GB["video_mlx:ltx-2.5-q4-704"] >= 24.0
        assert _admission.MEDIA_MODEL_MEMORY_GB["video_mlx:wan2.2-5b"] >= 20.0

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


class TestMemoryCoordination:
    async def test_admit_skips_reclaim_when_enough_free_memory(self, monkeypatch):
        called = False

        async def fake_free() -> float:
            return 40.0

        async def fake_reclaim(_need: float) -> list[dict[str, str]]:
            nonlocal called
            called = True
            return []

        monkeypatch.setattr(_admission, "free_unified_gb", fake_free)
        monkeypatch.setattr(_admission, "request_pipeline_reclaim", fake_reclaim)
        assert await _admission.admit("mflux:schnell") is None
        assert called is False

    async def test_admit_posts_authenticated_reclaim_and_waits_for_memory(self, monkeypatch):
        samples = iter([10.0, 28.0])
        requests: list[tuple[str, dict[str, str], dict[str, float]]] = []

        async def fake_free() -> float:
            return next(samples)

        class FakeResp:
            status_code = 200
            text = '{"unloads": [{"engine": "ollama", "model": "qwen", "status": "requested"}]}'

            def json(self) -> dict[str, object]:
                return {"unloads": [{"engine": "ollama", "model": "qwen", "status": "requested"}]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url: str, headers: dict[str, str], json: dict[str, float]):
                requests.append((url, headers, json))
                return FakeResp()

        monkeypatch.setenv("PIPELINE_API_KEY", "secret-key")
        monkeypatch.setenv("PORTAL_PIPELINE_URL", "http://127.0.0.1:9099")
        monkeypatch.setattr(_admission, "free_unified_gb", fake_free)
        monkeypatch.setattr(_admission.httpx, "AsyncClient", FakeClient)

        # mflux:schnell needs 15 + 4 = 19 GB; initial free is 10 -> shortfall 9.0 GB
        assert await _admission.admit("mflux:schnell") is None
        assert len(requests) == 1
        url, headers, body = requests[0]
        assert url == "http://127.0.0.1:9099/admin/reclaim-idle"
        assert headers["Authorization"] == "Bearer secret-key"
        assert body["need_gib"] == 9.0

    async def test_admit_refuses_when_memory_remains_low_after_reclaim(self, monkeypatch):
        async def fake_free() -> float:
            return 8.0

        async def fake_reclaim(_need: float) -> list[dict[str, str]]:
            return []

        monkeypatch.setattr(_admission, "free_unified_gb", fake_free)
        monkeypatch.setattr(_admission, "request_pipeline_reclaim", fake_reclaim)
        refusal = await _admission.admit("mflux:schnell")
        assert refusal is not None
        assert refusal["success"] is False
        assert refusal["retryable"] is True

    async def test_music_releases_cached_pipeline_after_idle_timeout(self, monkeypatch):
        import sys
        import types

        import portal.modules.media.tools.music_minimax_mcp as music_mcp

        cleared = False
        fake_mlx = types.ModuleType("mlx")
        fake_core = types.ModuleType("mlx.core")

        def fake_clear() -> None:
            nonlocal cleared
            cleared = True

        fake_core.clear_cache = fake_clear  # type: ignore[attr-defined]
        fake_mlx.core = fake_core  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
        monkeypatch.setitem(sys.modules, "mlx.core", fake_core)

        music_mcp._pipeline_cache = object()
        released = music_mcp._release_pipeline(exit_on_idle=False)
        assert released is True
        assert music_mcp._pipeline_cache is None
        assert cleared is True
