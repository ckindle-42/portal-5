"""Unit tests for the shared media async job manager and MCP start/status contracts."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from portal.modules.media.tools import _jobs
from portal.modules.media.tools._jobs import JobDurationStats, MediaJobManager, start_reply
from portal.platform.inference.router.tool_repeat import is_read_only


def test_status_wait_contract_covers_a_whole_job() -> None:
    assert _jobs.DEFAULT_STATUS_WAIT_S <= 30
    assert _jobs.MAX_STATUS_WAIT_S >= 120
    assert _jobs.STATUS_TOOL_TIMEOUT_S > _jobs.MAX_STATUS_WAIT_S


def test_media_start_reply_defers_polling_to_a_later_turn() -> None:
    reply = start_reply("job-123", "music_status", "model=acestep")

    assert reply["job_id"] == "job-123"
    assert "continues asynchronously" in reply["message"]
    assert "later turn" in reply["message"]
    assert "do not poll in this turn" in reply["message"].lower()
    assert "music_status" in reply["next_action"]


def test_media_start_reply_states_the_eta() -> None:
    reply = start_reply("job-123", "music_status", "model=acestep", eta_s=250.4)

    assert reply["eta_s"] == 250
    assert "250s" in reply["message"]
    assert "continues asynchronously" in reply["message"]
    assert "do not poll in this turn" in reply["message"].lower()


def test_duration_stats_eta_uses_measured_durations_with_a_margin(tmp_path: Path) -> None:
    stats = JobDurationStats(tmp_path / "stats.json")
    assert stats.eta_s("music:acestep:30s", 300.0) == 300.0
    stats.observe("music:acestep:30s", 100.0)
    assert stats.eta_s("music:acestep:30s", 300.0) == 100.0 * _jobs.ETA_MARGIN
    reloaded = JobDurationStats(tmp_path / "stats.json")
    assert reloaded.eta_s("music:acestep:30s", 300.0) == stats.eta_s("music:acestep:30s", 300.0)


@pytest.mark.asyncio
async def test_single_status_call_after_start_delivers_the_artifact(tmp_path: Path) -> None:
    stats = JobDurationStats(tmp_path / "stats.json")
    mgr = MediaJobManager(default_wait_s=0.0, max_wait_s=5.0, stats=stats)

    async def runner(progress: Any) -> dict[str, Any]:
        progress(2, "Generating (acestep, 8 steps)…")
        await asyncio.sleep(0.25)
        return {"success": True, "download_url": "http://x/song.wav", "url": "http://x/song.wav"}

    job_id = mgr.start(runner, eta_key="music:acestep:30s", eta_s=0.4)
    res = await mgr.status(job_id, wait_s=0.0)  # the ETA alone must carry one call to done
    assert res["status"] == "done"
    assert res["download_url"] == "http://x/song.wav"
    assert "http://x/song.wav" in res["message"]
    assert stats.eta_s("music:acestep:30s", 300.0) < 5.0  # measured duration replaced default


@pytest.mark.asyncio
async def test_status_without_eta_returns_running_without_waiting() -> None:
    mgr = MediaJobManager(default_wait_s=0.0, max_wait_s=5.0)
    gate = asyncio.Event()

    async def runner(_progress: Any) -> dict[str, Any]:
        await gate.wait()
        return {"success": True}

    job_id = mgr.start(runner)
    t0 = time.monotonic()
    res = await mgr.status(job_id, wait_s=0.0)
    assert res["status"] == "running"
    assert time.monotonic() - t0 < 0.5
    gate.set()


@pytest.mark.asyncio
async def test_failed_job_is_reported_as_a_failure_not_still_running() -> None:
    mgr = MediaJobManager(default_wait_s=1.0, max_wait_s=1.0)

    async def runner(_progress: Any) -> dict[str, Any]:
        return {"success": False, "error": "insufficient memory"}

    res = await mgr.status(mgr.start(runner))
    assert res["status"] == "error"
    assert res["error"] == "insufficient memory"
    assert res["message"] == "Job failed: insufficient memory"
    assert "Report this failure" in res["next_action"]


@pytest.mark.asyncio
async def test_crashed_job_is_reported_as_a_failure() -> None:
    mgr = MediaJobManager(default_wait_s=1.0, max_wait_s=1.0)

    async def runner(_progress: Any) -> dict[str, Any]:
        raise ValueError("boom")

    res = await mgr.status(mgr.start(runner))
    assert res["status"] == "error"
    assert res["message"] == "Job failed: boom"
    assert "Report this failure" in res["next_action"]


@pytest.mark.asyncio
async def test_default_status_call_waits_out_a_slow_job() -> None:
    mgr = MediaJobManager(default_wait_s=0.3, max_wait_s=0.3)

    async def runner(progress: Any) -> dict[str, Any]:
        progress(2, "Generating")
        await asyncio.sleep(0.1)
        return {"success": True, "url": "http://x/song.wav", "download_url": "http://x/song.wav"}

    job_id = mgr.start(runner)
    res = await mgr.status(job_id)  # no wait_s: the default alone must reach done
    assert res["status"] == "done"
    assert res["download_url"] == "http://x/song.wav"


@pytest.mark.asyncio
async def test_done_message_carries_the_download_link() -> None:
    mgr = MediaJobManager(default_wait_s=1.0, max_wait_s=1.0)

    async def runner(progress: Any) -> dict[str, Any]:
        progress(2, "Generating (acestep, 8 steps)…")
        return {"success": True, "url": "http://x/s.wav", "download_url": "http://x/s.wav"}

    job_id = mgr.start(runner)
    res = await mgr.status(job_id)
    assert res["status"] == "done"
    assert "http://x/s.wav" in res["message"]
    assert "Generating" not in res["message"]
    assert "error" not in res


@pytest.mark.asyncio
async def test_done_snapshot_drops_a_log_line_stuffed_into_error() -> None:
    mgr = MediaJobManager(default_wait_s=1.0, max_wait_s=1.0)

    async def runner(_progress: Any) -> dict[str, Any]:
        return {
            "success": True,
            "download_url": "http://x/s.wav",
            "error": "VAE decode completed. Preparing audio tensors...",
        }

    res = await mgr.status(mgr.start(runner))
    assert res["status"] == "done"
    assert res["download_url"] == "http://x/s.wav"
    assert "error" not in res


@pytest.mark.asyncio
async def test_running_snapshot_says_to_wait_not_answer() -> None:
    mgr = MediaJobManager(default_wait_s=0.05, max_wait_s=0.05)
    gate = asyncio.Event()

    async def runner(_progress: Any) -> dict[str, Any]:
        await gate.wait()
        return {"success": True}

    job_id = mgr.start(runner)
    res = await mgr.status(job_id)
    assert res["status"] == "running"
    assert "again" in res["next_action"] and "later turn" in res["next_action"]
    gate.set()
    assert (await mgr.status(job_id))["status"] == "done"


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
    assert "http://x/song" in mus_done["message"]
