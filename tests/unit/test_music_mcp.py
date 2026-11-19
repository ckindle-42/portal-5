"""Music MCP contract: start/status, reclaim-before-worker, idle flag. No network."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from portal.modules.media.tools import _admission
from portal.modules.media.tools.music_worker import generate, write_wav


@pytest.fixture
def music_mod(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import portal.modules.media.tools.music_mcp as music_mcp

    monkeypatch.setattr(music_mcp, "get_generated_dir", lambda _category: tmp_path)
    monkeypatch.setattr(music_mcp, "_engine_ready", lambda _engine: (True, ""))
    music_mcp._weights_resident = False
    return music_mcp


def test_worker_rejects_unknown_task() -> None:
    result = generate({"engine": "acestep", "upstream_task": "nope", "seed": 1})
    assert result["success"] is False


def test_write_wav_is_riff(tmp_path: Path) -> None:
    dest = tmp_path / "tone.wav"
    write_wav(str(dest), [0.0, 0.1, -0.1], 48_000)
    header = dest.read_bytes()[:12]
    assert dest.stat().st_size > 44
    assert header[:4] == b"RIFF" and header[8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_music_start_long_polls_to_artifact(
    music_mod, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def fake_admit(_key: str) -> None:
        return None

    async def fake_worker(spec: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        path = Path(spec["output_path"])
        path.write_bytes(b"RIFF")
        return {"success": True, "artifact_path": str(path)}

    async def fake_publish(path: Path) -> dict[str, str]:
        return {"url": "http://x/song", "filename": path.name}

    monkeypatch.setattr(music_mod, "admit", fake_admit)
    monkeypatch.setattr(music_mod, "run_worker", fake_worker)
    monkeypatch.setattr(music_mod, "publish_file", fake_publish)

    started = await music_mod.music_start(prompt="piano", seconds=15, steps=8, seed=42)
    assert started["success"] is True and started["job_id"]
    assert started["engine"] == "acestep"
    done = await music_mod.music_status(started["job_id"], wait_s=2.0)
    assert done["status"] == "done"
    assert done["artifact_path"].endswith(".wav")
    assert str(tmp_path) in done["artifact_path"]


@pytest.mark.asyncio
async def test_music_start_rejects_unknown_engine_and_edit_without_source(music_mod) -> None:
    unknown = await music_mod.music_start(prompt="piano", engine="nope")
    assert unknown["success"] is False
    missing = await music_mod.music_start(prompt="piano", task_type="repaint")
    assert missing["success"] is False and "source" in missing["error"]


@pytest.mark.asyncio
async def test_music_start_reclaims_before_the_worker(
    music_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    samples = iter([1.0, 40.0, 40.0])

    async def fake_free() -> float:
        return next(samples)

    async def fake_reclaim(need: float) -> list[dict[str, str]]:
        order.append(f"reclaim:{need:.1f}")
        return []

    async def fake_worker(spec: dict[str, Any]) -> dict[str, Any]:
        order.append("worker")
        path = Path(spec["output_path"])
        path.write_bytes(b"RIFF")
        return {"success": True, "artifact_path": str(path)}

    async def fake_publish(path: Path) -> dict[str, str]:
        return {"url": "http://x/song", "filename": path.name}

    monkeypatch.setattr(_admission, "free_unified_gb", fake_free)
    monkeypatch.setattr(_admission, "request_pipeline_reclaim", fake_reclaim)
    monkeypatch.setattr(music_mod, "run_worker", fake_worker)
    monkeypatch.setattr(music_mod, "publish_file", fake_publish)

    started = await music_mod.music_start(prompt="piano", seed=1)
    done = await music_mod.music_status(started["job_id"], wait_s=2.0)
    assert done["status"] == "done"
    assert order[0].startswith("reclaim:")
    assert order.index("worker") > 0
    needed = _admission.MEDIA_MODEL_MEMORY_GB["music:acestep-xl-turbo"]
    assert order[0] == f"reclaim:{needed + _admission.MEMORY_HEADROOM_GB - 1.0:.1f}"
