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


def test_comfyui_launcher_does_not_override_model_inference_dtype():
    services = (REPO / "scripts/lib/services.sh").read_text()
    installer = services.split("_launch_install_comfyui()", 1)[1].split("\n}", 1)[0]
    assert "--force-fp16" not in installer


def test_qwen_installer_uses_verified_mps_checkpoints():
    services = (REPO / "scripts/lib/services.sh").read_text()
    installer = services.split("_launch_pull_qwen_image()", 1)[1]
    assert "qwen_image_fp8_e4m3fn.safetensors" in installer
    assert "qwen_image_edit_2509_fp8_e4m3fn.safetensors" in installer
    assert "qwen_image_2512_bf16.safetensors" not in installer
    assert "qwen_image_edit_2511_bf16.safetensors" not in installer


def test_routine_rebuilds_do_not_restart_shelved_video_service():
    launch = (REPO / "launch.sh").read_text()
    assert "mcp-video" not in launch


def test_qwen_edit_2509_route_builds_distinct_workflow():
    from portal.modules.media.tools import comfyui_mcp

    workflow, seed = comfyui_mcp._build_image_workflow(
        prompt="make the suit green",
        width=512,
        height=512,
        steps=20,
        cfg=4.0,
        negative_prompt="",
        seed=2509,
        model="qwen-image-edit-2509",
        checkpoint="",
        lora="",
        lora_strength=1.0,
        image_filename="source.png",
    )

    assert seed == 2509
    assert workflow["12"]["inputs"]["unet_name"] == ("qwen_image_edit_2509_fp8_e4m3fn.safetensors")
    assert workflow["41"]["inputs"]["image"] == "source.png"
    assert workflow["68"]["inputs"]["prompt"] == "make the suit green"
    assert workflow["66"]["inputs"]["width"] == 512
    assert workflow["66"]["inputs"]["height"] == 512


@pytest.mark.asyncio
async def test_http_dispatch_forwards_image_url():
    from portal.modules.media.tools import comfyui_mcp

    for tool_name in ("start_image_generation", "generate_image"):
        manifest = next(tool for tool in comfyui_mcp.TOOLS_MANIFEST if tool["name"] == tool_name)
        assert "image_url" in manifest["parameters"]["properties"]

    request = AsyncMock()
    request.json.return_value = {
        "arguments": {
            "prompt": "make the suit green",
            "model": "qwen-image-edit-2509",
            "image_url": "/workspace/uploads/source.png",
        }
    }
    with patch.object(
        comfyui_mcp,
        "start_image_generation",
        AsyncMock(return_value={"success": True, "job_id": "test-job"}),
    ) as start:
        await comfyui_mcp.start_image_generation_endpoint(request)

    assert start.await_args.kwargs["image_url"] == "/workspace/uploads/source.png"

    with patch.object(
        comfyui_mcp,
        "generate_image",
        AsyncMock(return_value={"success": True, "filename": "test.png"}),
    ) as generate:
        await comfyui_mcp.generate_image_endpoint(request)

    assert generate.await_args.kwargs["image_url"] == "/workspace/uploads/source.png"


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

    def test_music_models_use_live_complete_quality_estimates(self):
        assert _admission.MEDIA_MODEL_MEMORY_GB["music:minimax3"] == 27.0
        assert _admission.MEDIA_MODEL_MEMORY_GB["music:acestep-sft"] == 40.0

    def test_headroom_constant_exists(self):
        assert _admission.MEMORY_HEADROOM_GB >= 0

    def test_qwen_edit_2509_uses_measured_estimate(self):
        assert _admission.MEDIA_MODEL_MEMORY_GB["comfyui:qwen-image-edit-2509"] == 38.0


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


class TestFreeGbFromVmStat:
    """Regression for a false admission refusal: ACE-Step (~40GB) was refused
    with 35.6GB reported free by vm_stat while ComfyUI's own psutil-based
    system_stats reported 44GB free at the same instant — free+inactive
    matched ComfyUI within 0.1GB, free-alone did not."""

    _VM_STAT_OUT = (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free:                                  2330580.\n"
        "Pages active:                                 472285.\n"
        "Pages inactive:                               562220.\n"
        "Pages speculative:                              2619.\n"
    )

    def test_includes_inactive_pages(self):
        with patch("subprocess.check_output", return_value=self._VM_STAT_OUT.encode()):
            free_gb = _admission._free_gb_from_vm_stat()
        assert free_gb is not None
        assert free_gb == pytest.approx(44.14, abs=0.01)

    def test_returns_none_when_inactive_missing(self):
        out = "Pages free:                                  2330580.\n"
        with patch("subprocess.check_output", return_value=out.encode()):
            assert _admission._free_gb_from_vm_stat() is None


class TestMediaModelMemoryDictInSyncWithWikiFact:
    """_admission.py's docstring explains MEDIA_MODEL_MEMORY_GB is deliberately
    NOT imported from seed_facts.py (Rule 3: MCP modules stay independent) but
    kept as a manually-synced copy instead. Regression test for drift going
    uncaught — see unit-known-limitations-qwen-image-bf16-crashes-on-apple-
    silicon-mps."""

    def test_tables_match(self):
        import portal.platform.wiki.adapters.seed_facts as seed_facts

        assert seed_facts.MEDIA_MODEL_MEMORY_GB == _admission.MEDIA_MODEL_MEMORY_GB, (
            "portal/modules/media/tools/_admission.py's MEDIA_MODEL_MEMORY_GB "
            "has drifted from portal/platform/wiki/adapters/seed_facts.py's copy "
            "— update both together."
        )
