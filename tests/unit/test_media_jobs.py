"""Unit tests for the shared media async job manager and MCP start/status contracts."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from portal.modules.media.tools._jobs import MediaJobManager
from portal.platform.inference.router.tool_repeat import is_read_only


@pytest.mark.asyncio
async def test_job_manager_start_fast_and_status_long_polls_to_completion() -> None:
    mgr = MediaJobManager(default_wait_s=5.0, max_wait_s=10.0)

    async def runner(progress: Any) -> dict[str, Any]:
        progress(1, "Working")
        await asyncio.sleep(0.05)
        return {"success": True, "artifact_path": "/tmp/out.png", "url": "http://owui/f.png"}

    t0 = time.monotonic()
    job_id = mgr.start(runner)
    start_elapsed = time.monotonic() - t0
    assert start_elapsed < 0.04

    res = await mgr.status(job_id, wait_s=5.0)
    assert res["status"] == "done"
    assert res["artifact_path"] == "/tmp/out.png"
    assert res["url"] == "http://owui/f.png"
    assert time.monotonic() - t0 < 1.0  # returned immediately on finish, not full 5s


@pytest.mark.asyncio
async def test_job_manager_status_bounds_wait_and_reports_progress_while_running() -> None:
    mgr = MediaJobManager(default_wait_s=0.05, max_wait_s=0.1)
    gate = asyncio.Event()

    async def runner(progress: Any) -> dict[str, Any]:
        progress(2, "Step 4/8")
        await gate.wait()
        return {"success": True, "artifact_path": "/tmp/done.mp4"}

    job_id = mgr.start(runner)
    await asyncio.sleep(0.01)

    t0 = time.monotonic()
    running = await mgr.status(job_id, wait_s=99.0)  # clamped to max_wait_s=0.1
    elapsed = time.monotonic() - t0
    assert 0.08 <= elapsed < 0.5
    assert running["status"] == "running"
    assert running["stage"] == 2
    assert running["message"] == "Step 4/8"

    gate.set()
    done = await mgr.status(job_id, wait_s=1.0)
    assert done["status"] == "done"
    assert done["artifact_path"] == "/tmp/done.mp4"


@pytest.mark.asyncio
async def test_job_manager_unknown_job_returns_immediately() -> None:
    mgr = MediaJobManager(default_wait_s=5.0, max_wait_s=10.0)
    t0 = time.monotonic()
    res = await mgr.status("missing123", wait_s=5.0)
    assert res["status"] == "unknown"
    assert time.monotonic() - t0 < 0.1


@pytest.mark.asyncio
async def test_job_manager_serializes_jobs_and_propagates_errors() -> None:
    mgr = MediaJobManager(default_wait_s=1.0, max_wait_s=2.0)
    order: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def job1(_progress: Any) -> dict[str, Any]:
        order.append("1-start")
        first_started.set()
        await release_first.wait()
        order.append("1-end")
        return {"success": True, "artifact_path": "/tmp/1.wav"}

    async def job2(_progress: Any) -> dict[str, Any]:
        order.append("2-start")
        return {"success": False, "error": "oom"}

    j1 = mgr.start(job1)
    await first_started.wait()
    j2 = mgr.start(job2)

    snap2 = await mgr.status(j2, wait_s=0.0)
    assert snap2["status"] == "queued"

    release_first.set()
    r1 = await mgr.status(j1, wait_s=1.0)
    r2 = await mgr.status(j2, wait_s=1.0)
    assert r1["status"] == "done"
    assert r2["status"] == "error"
    assert r2["error"] == "oom"
    assert order == ["1-start", "1-end", "2-start"]


@pytest.mark.asyncio
async def test_job_manager_idle_callback_fires_and_cancels_on_new_job() -> None:
    idle_calls = 0

    async def on_idle() -> None:
        nonlocal idle_calls
        idle_calls += 1

    mgr = MediaJobManager(idle_timeout_s=0.08, on_idle=on_idle)

    async def quick(_progress: Any) -> dict[str, Any]:
        return {"success": True}

    j1 = mgr.start(quick)
    await mgr.status(j1, wait_s=1.0)
    await asyncio.sleep(0.03)
    assert idle_calls == 0

    j2 = mgr.start(quick)  # cancels pending idle timer
    await mgr.status(j2, wait_s=1.0)
    await asyncio.sleep(0.03)
    assert idle_calls == 0

    await asyncio.sleep(0.1)
    assert idle_calls == 1


def test_media_status_tools_are_not_cached_by_tool_repeat_guard() -> None:
    for name in ("image_status", "video_status", "music_status"):
        assert not is_read_only(name), name


@pytest.mark.asyncio
async def test_media_mcps_start_and_long_poll_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import portal.modules.media.tools.mflux_mcp as mflux_mcp
    import portal.modules.media.tools.music_mcp as music_mcp
    import portal.modules.media.tools.video_mlx_mcp as video_mcp

    async def fake_admit(_key: str) -> None:
        return None

    async def fake_mflux_gen(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.02)
        return {"success": True, "artifact_path": str(tmp_path / "img.png"), "url": "http://x/img"}

    async def fake_video_gen(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.02)
        return {"success": True, "artifact_path": str(tmp_path / "vid.mp4"), "url": "http://x/vid"}

    async def fake_music_worker(spec: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.02)
        return {"success": True, "artifact_path": str(spec["output_path"])}

    async def fake_publish(path: Path) -> dict[str, Any]:
        return {"url": "http://x/song", "filename": Path(path).name}

    monkeypatch.setattr(mflux_mcp, "admit", fake_admit)
    monkeypatch.setattr(mflux_mcp, "_generate", fake_mflux_gen)
    monkeypatch.setattr(video_mcp, "admit", fake_admit)
    monkeypatch.setattr(video_mcp, "_generate", fake_video_gen)
    monkeypatch.setattr(music_mcp, "admit", fake_admit)
    monkeypatch.setattr(music_mcp, "_engine_ready", lambda _engine: (True, ""))
    monkeypatch.setattr(music_mcp, "get_generated_dir", lambda _category: tmp_path)
    monkeypatch.setattr(music_mcp, "run_worker", fake_music_worker)
    monkeypatch.setattr(music_mcp, "publish_file", fake_publish)

    img_start = await mflux_mcp.image_start(prompt="cat")
    assert img_start["success"] is True and img_start["job_id"]
    img_done = await mflux_mcp.image_status(img_start["job_id"], wait_s=2.0)
    assert img_done["status"] == "done" and img_done["artifact_path"].endswith("img.png")

    vid_start = await video_mcp.video_start(prompt="waves")
    assert vid_start["success"] is True and vid_start["job_id"]
    vid_done = await video_mcp.video_status(vid_start["job_id"], wait_s=2.0)
    assert vid_done["status"] == "done" and vid_done["artifact_path"].endswith("vid.mp4")

    mus_start = await music_mcp.music_start(prompt="ambient")
    assert mus_start["success"] is True and mus_start["job_id"]
    mus_done = await music_mcp.music_status(mus_start["job_id"], wait_s=2.0)
    assert mus_done["status"] == "done" and mus_done["artifact_path"].endswith(".wav")
