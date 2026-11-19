"""Music MCP contract: start/status, reclaim-before-worker, idle flag. No network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from portal.modules.media.tools import _admission
from portal.modules.media.tools.music_worker import (
    _adopt_artifact,
    generate,
    interpret_worker_output,
    write_wav,
)


def test_adopt_artifact_removes_the_engine_duplicate(tmp_path: Path) -> None:
    produced = tmp_path / "04e7b754-4def-e05e-366e-8379475fbd1c.wav"
    produced.write_bytes(b"RIFFdata")
    dest = tmp_path / "music_164fe8ba6c14.wav"
    _adopt_artifact(produced, dest)
    assert dest.read_bytes() == b"RIFFdata"
    assert not produced.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["music_164fe8ba6c14.wav"]


_VAE_LOG = (
    "2026-11-19 08:54:52.123 | INFO     | acestep.core.generation.handler."
    "generate_music_payload:_build_generate_music_success_payload:38 - "
    "[generate_music] VAE decode completed. Preparing audio tensors...\n"
)


def test_log_line_stderr_keeps_a_finished_wav(tmp_path: Path) -> None:
    # Live p5-9da545bd4379: the wav was on disk and music_status's error was this log line.
    dest = tmp_path / "music_cc401819a61d.wav"
    dest.write_bytes(b"RIFF" + b"\x00" * 64)
    result = interpret_worker_output(b"", _VAE_LOG.encode(), -9, str(dest))
    assert result["success"] is True
    assert result["artifact_path"] == str(dest)
    assert "error" not in result


def test_explicit_worker_failure_is_not_recovered(tmp_path: Path) -> None:
    dest = tmp_path / "music_partial.wav"
    dest.write_bytes(b"RIFF" + b"\x00" * 64)
    body = b'{"success": false, "error": "ACE-Step returned no audio"}'
    result = interpret_worker_output(body, b"", 1, str(dest))
    assert result["success"] is False
    assert result["error"] == "ACE-Step returned no audio"


def test_stdout_json_wins_over_a_trailing_log(tmp_path: Path) -> None:
    dest = tmp_path / "music_ok.wav"
    payload = json.dumps({"success": True, "artifact_path": str(dest), "sample_rate": 48000})
    out = (_VAE_LOG + payload).encode()
    result = interpret_worker_output(out, _VAE_LOG.encode(), 0, str(dest))
    assert result["success"] is True
    assert result["artifact_path"] == str(dest)


def test_adopt_artifact_same_path_is_a_noop(tmp_path: Path) -> None:
    dest = tmp_path / "music_job.wav"
    dest.write_bytes(b"RIFFdata")
    _adopt_artifact(dest, dest)
    assert dest.read_bytes() == b"RIFFdata"


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
