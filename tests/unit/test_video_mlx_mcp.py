"""Unit tests for the video MCP's async tool contract, engine commands, and
size-aware admission keys. No network, no real renderer subprocess."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import portal.modules.media.tools.video_mlx_mcp as video_mcp
from portal.modules.media.tools import _admission
from portal.platform.inference.router.tool_repeat import is_read_only


def _tools() -> dict[str, Any]:
    return {t.name: t for t in asyncio.run(video_mcp.mcp.list_tools())}


class TestToolContract:
    def test_surface_is_the_shared_async_pattern(self):
        assert set(_tools()) == {"video_start", "video_status", "video_models"}

    def test_status_tool_polls_are_never_cached_by_tool_repeat_guard(self):
        assert not is_read_only("video_status")

    def test_status_tool_declares_a_long_dispatch_timeout(self):
        meta = _tools()["video_status"].meta or {}
        assert meta.get("portal5/timeout_s", 0) > 60


class TestSizeAwareAdmissionKey:
    def test_ltx_key_buckets_by_resolution(self):
        assert video_mcp._media_model_key("ltx-2.5-q4", 512, 320) == "video_mlx:ltx-2.5-q4-512"
        assert video_mcp._media_model_key("ltx-2.5-q4", 704, 480) == "video_mlx:ltx-2.5-q4-704"

    def test_wan_key_has_no_size_bucket(self):
        assert video_mcp._media_model_key("wan2.2-5b", 704, 480) == "video_mlx:wan2.2-5b"


class TestEngineCommands:
    def test_ltx_fast_quality_uses_the_distilled_sampler(self):
        cfg = video_mcp._engine_cfg("ltx-2.5-q4")
        cmd = video_mcp._ltx_cmd(
            cfg, "waves", 97, 704, 480, 42, 24, Path("/o/out.mp4"), None, "fast"
        )
        assert cmd[0] == video_mcp.VIDEO_MLX_BIN and cmd[1] == "generate"
        assert "--distilled" in cmd and "--two-stage" not in cmd
        assert cmd[cmd.index("--model") + 1] == "dgrauet/ltx-2.5-mlx-q4"
        assert cmd[cmd.index("--frames") + 1] == "97"
        assert cmd[cmd.index("--output") + 1] == "/o/out.mp4"

    def test_ltx_hq_quality_uses_the_two_stage_pass(self):
        cfg = video_mcp._engine_cfg("ltx-2.5-q4")
        cmd = video_mcp._ltx_cmd(cfg, "waves", 97, 704, 480, 42, 24, Path("/o/out.mp4"), None, "hq")
        assert "--two-stage" in cmd and "--distilled" not in cmd

    def test_ltx_i2v_anchors_the_source_image_at_frame_zero(self):
        cfg = video_mcp._engine_cfg("ltx-2.5-q4")
        cmd = video_mcp._ltx_cmd(
            cfg, "waves", 97, 704, 480, 42, 24, Path("/o/out.mp4"), Path("/o/src.png"), "fast"
        )
        i = cmd.index("--image")
        assert cmd[i + 1 : i + 4] == ["/o/src.png", "0", "1.0"]

    def test_wan_command_targets_the_converted_model_dir(self):
        cfg = video_mcp._engine_cfg("wan2.2-5b")
        cmd = video_mcp._wan_cmd(cfg, "waves", 97, 704, 480, 42, Path("/o/out.mp4"), None)
        assert cmd[0] == video_mcp.VIDEO_MLX_WAN_BIN
        assert cmd[cmd.index("--model-dir") + 1] == "Anes1032/Wan2.2-TI2V-5B-mlx-q8"
        assert cmd[cmd.index("--num-frames") + 1] == "97"
        assert cmd[cmd.index("--output-path") + 1] == "/o/out.mp4"
        assert "--frame-rate" not in cmd  # the Wan CLI has no fps flag

    def test_wan_i2v_passes_the_image(self):
        cfg = video_mcp._engine_cfg("wan2.2-5b")
        cmd = video_mcp._wan_cmd(
            cfg, "waves", 97, 704, 480, 42, Path("/o/out.mp4"), Path("/o/src.png")
        )
        assert cmd[cmd.index("--image") + 1] == "/o/src.png"


class FakeProc:
    def __init__(self, out: Path):
        self._out = out
        self.returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        self._out.write_bytes(b"mp4")
        return b"", b""


async def _publish(path: Path) -> dict[str, str]:
    return {"url": f"http://owui/{path.name}"}


@pytest.mark.asyncio
async def test_generate_dispatches_per_engine_and_publishes(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        video_mcp.uuid, "uuid4", lambda: type("U", (), {"hex": "deadbeef"})(), raising=False
    )

    async def fake_exec(*cmd: str, **_kw: Any) -> FakeProc:
        argv = list(cmd)
        flag = "--output-path" if argv[0] == video_mcp.VIDEO_MLX_WAN_BIN else "--output"
        return FakeProc(Path(argv[argv.index(flag) + 1]))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(video_mcp, "publish_file", lambda p: _publish(p))

    ltx = await video_mcp._generate("waves", "ltx-2.5-q4", 97, 704, 480, 42, 24)
    assert ltx["success"] is True and ltx["engine"] == "ltx"
    assert ltx["artifact_path"].endswith("ltx_deadbeef.mp4")

    wan = await video_mcp._generate("waves", "wan2.2-5b", 97, 704, 480, 42, 24)
    assert wan["success"] is True and wan["engine"] == "wan"
    assert wan["artifact_path"].endswith("wan_deadbeef.mp4")


@pytest.mark.asyncio
async def test_generate_reports_the_renderer_stderr_on_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))

    class FailedProc:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"boom: weights missing"

    async def fake_exec(*_cmd: str, **_kw: Any) -> FailedProc:
        return FailedProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    reply = await video_mcp._generate("waves", "ltx-2.5-q4", 97, 704, 480, 42, 24)
    assert reply["success"] is False and "boom" in reply["error"]


class TestVideoStartLifecycle:
    @pytest.fixture(autouse=True)
    def _workspace(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))

    @pytest.mark.asyncio
    async def test_start_returns_job_id_and_status_long_polls_to_done(self, monkeypatch, tmp_path):
        async def fake_admit(_key: str) -> None:
            return None

        async def fake_gen(*_a: Any, **_k: Any) -> dict[str, Any]:
            return {
                "success": True,
                "artifact_path": str(tmp_path / "v.mp4"),
                "url": "http://x/v",
                "download_url": "http://x/v",
            }

        monkeypatch.setattr(video_mcp, "admit", fake_admit)
        monkeypatch.setattr(video_mcp, "_generate", fake_gen)

        start = await video_mcp.video_start(prompt="ocean waves at sunset", quality="fast")
        assert start["success"] is True and start["job_id"]
        assert start["next_action"] == f"call video_status with job_id='{start['job_id']}'"
        assert start["model"] == "ltx-2.5-q4" and start["quality"] == "fast"

        done = await video_mcp.video_status(start["job_id"], wait_s=2.0)
        assert done["status"] == "done"
        assert done["artifact_path"] == str(tmp_path / "v.mp4")
        assert done["download_url"] == "http://x/v"

    @pytest.mark.asyncio
    async def test_start_rejects_unknown_quality_without_admitting(self, monkeypatch):
        def boom(_key: str) -> None:
            raise AssertionError("admit must not run for an invalid quality")

        monkeypatch.setattr(video_mcp, "admit", boom)
        reply = await video_mcp.video_start(prompt="waves", quality="cinematic")
        assert reply["success"] is False and "quality" in reply["error"]

    @pytest.mark.asyncio
    async def test_start_admits_with_the_size_aware_key_before_load(self, monkeypatch, tmp_path):
        keys: list[str] = []

        async def fake_admit(key: str) -> None:
            keys.append(key)

        async def fake_gen(*_a: Any, **_k: Any) -> dict[str, Any]:
            return {"success": True}

        monkeypatch.setattr(video_mcp, "admit", fake_admit)
        monkeypatch.setattr(video_mcp, "_generate", fake_gen)
        await video_mcp.video_start(prompt="waves", width=704, height=480)
        await video_mcp.video_start(prompt="waves", width=512, height=320)
        await video_mcp.video_start(prompt="waves", model="wan2.2-5b")
        assert set(keys) == {
            "video_mlx:ltx-2.5-q4-704",
            "video_mlx:ltx-2.5-q4-512",
            "video_mlx:wan2.2-5b",
        }

    @pytest.mark.asyncio
    async def test_admitted_job_asks_the_pipeline_to_reclaim_idle_memory_first(
        self, monkeypatch, tmp_path
    ):
        """Memory reclaim before load: with 10GB free, the 512-bucket job (18+4)
        must drive admit() into a 12GB /admin/reclaim-idle call, then proceed."""
        reclaims: list[float] = []

        async def fake_free() -> float:
            return 40.0 if reclaims else 10.0

        async def fake_reclaim(need_gib: float) -> list[dict[str, str]]:
            reclaims.append(need_gib)
            return []

        monkeypatch.setattr(_admission, "free_unified_gb", fake_free)
        monkeypatch.setattr(_admission, "request_pipeline_reclaim", fake_reclaim)

        async def fake_gen(*_a: Any, **_k: Any) -> dict[str, Any]:
            return {"success": True}

        monkeypatch.setattr(video_mcp, "_generate", fake_gen)

        start = await video_mcp.video_start(prompt="waves", width=512, height=320)
        assert start["success"] is True
        done = await video_mcp.video_status(start["job_id"], wait_s=2.0)
        assert done["status"] == "done"
        assert reclaims == [12.0]

    @pytest.mark.asyncio
    async def test_status_of_unknown_job_answers_immediately(self):
        reply = await video_mcp.video_status("nosuchjob", wait_s=0.0)
        assert reply["status"] == "unknown"


class TestVideoModels:
    @pytest.mark.asyncio
    async def test_roster_reports_engine_audio_and_default(self):
        reply = await video_mcp.video_models()
        assert reply["success"] is True
        roster = reply["models"]
        assert roster["ltx-2.5-q4"]["audio"] is True
        assert roster["ltx-2.5-q4"]["default"] is True
        assert roster["wan2.2-5b"]["audio"] is False  # silent MP4, no audio stream
        assert roster["wan2.2-5b"]["installed"] is False  # HF id default, not a local dir


def test_frame_grid_floors_to_the_engine_grid() -> None:
    assert video_mcp._round_frames(97, 8) == 97  # already 8k+1
    assert video_mcp._round_frames(100, 8) == 97
    assert video_mcp._round_frames(97, 4) == 97  # already 4n+1
    assert video_mcp._round_frames(100, 4) == 97
    assert video_mcp._round_frames(3, 8) == 9  # floor never goes under the minimum


def test_engine_cfg_passes_unknown_keys_through_as_ltx_tags() -> None:
    assert video_mcp._engine_cfg("future-pack") == {"engine": "ltx", "model": "future-pack"}
