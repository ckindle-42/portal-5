"""S9: Speech-to-Text tests."""

import contextlib
import time
import uuid
from pathlib import Path

import httpx

from tests.acceptance._common import (
    MCP,
    MLX_SPEECH_URL,
    _get,
    record,
)


async def run() -> None:
    """S9: Speech-to-Text tests."""
    print("\n━━━ S9. SPEECH-TO-TEXT ━━━")
    sec = "S9"

    # Check if MLX Speech is available for ASR
    t0 = time.time()
    code, _ = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)

    if code == 200:
        record(sec, "S9-01", "MLX Speech ASR available", "PASS", "Qwen3-ASR", t0=t0)
    else:
        record(
            sec,
            "S9-01",
            "MLX Speech ASR available",
            "INFO",
            "not running (Docker Whisper fallback)",
            t0=t0,
        )

        # Check Docker Whisper
        t0 = time.time()
        code, _ = await _get(f"http://localhost:{MCP['whisper']}/health")
        record(
            sec,
            "S9-02",
            "Docker Whisper health",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )

    # S9-03: MLX Transcribe service health
    t0 = time.time()
    mlx_transcribe_code, _ = await _get("http://localhost:8924/health", timeout=5)
    record(
        sec,
        "S9-03",
        "MLX Transcribe health",
        "PASS" if mlx_transcribe_code == 200 else "INFO",
        f"HTTP {mlx_transcribe_code}"
        if mlx_transcribe_code == 200
        else "not running (start with ./launch.sh start-transcribe)",
        t0=t0,
    )

    # S9-04: MLX Transcribe end-to-end with fixture (only if service is up)
    if mlx_transcribe_code == 200:
        t0 = time.time()
        fixture = Path("tests/fixtures/audio/two_speaker_10s.wav")
        if not fixture.exists():
            record(sec, "S9-04", "MLX Transcribe diarization", "INFO", "fixture missing", t0=t0)
        else:
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    with open(fixture, "rb") as f:
                        files = {"file": (fixture.name, f, "audio/wav")}
                        r = await client.post(
                            "http://localhost:8924/v1/audio/transcribe-with-speakers",
                            files=files,
                            data={"num_speakers": "2"},
                        )
                if r.status_code == 200:
                    result = r.json()
                    spk_count = result.get("speaker_count", 0)
                    total_s = result.get("timing", {}).get("total_s", 0)
                    if spk_count >= 2 and total_s < 60:
                        record(
                            sec,
                            "S9-04",
                            "MLX Transcribe diarization",
                            "PASS",
                            f"{spk_count} speakers in {total_s:.1f}s",
                            t0=t0,
                        )
                    elif spk_count >= 2:
                        record(
                            sec,
                            "S9-04",
                            "MLX Transcribe diarization",
                            "WARN",
                            f"{spk_count} speakers but slow ({total_s:.1f}s)",
                            t0=t0,
                        )
                    else:
                        record(
                            sec,
                            "S9-04",
                            "MLX Transcribe diarization",
                            "WARN",
                            f"only {spk_count} speaker(s) detected",
                            t0=t0,
                        )
                else:
                    record(
                        sec,
                        "S9-04",
                        "MLX Transcribe diarization",
                        "FAIL",
                        f"HTTP {r.status_code}: {r.text[:100]}",
                        t0=t0,
                    )
            except Exception as e:
                record(sec, "S9-04", "MLX Transcribe diarization", "FAIL", str(e)[:100], t0=t0)
    else:
        t0 = time.time()
        record(sec, "S9-04", "MLX Transcribe diarization", "INFO", "service not running", t0=t0)

    # S9-05: MCP tool resolves OWUI-style upload (workspace integration)
    if mlx_transcribe_code == 200:
        t0 = time.time()
        fixture = Path("tests/fixtures/audio/two_speaker_10s.wav")
        if not fixture.exists():
            record(sec, "S9-05", "Workspace upload resolution", "INFO", "fixture missing", t0=t0)
        else:
            from portal.platform.mcp_host.workspace import get_uploads_dir

            uploads = get_uploads_dir()
            test_id = f"test_{uuid.uuid4().hex[:8]}"
            target = uploads / f"{test_id}_two_speaker.wav"
            target.write_bytes(fixture.read_bytes())
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    r = await client.post(
                        "http://localhost:8924/mcp/tools/transcribe_with_speakers",
                        json={"file": test_id, "num_speakers": 2},
                    )
                if r.status_code == 200 and "error" not in r.text:
                    record(
                        sec,
                        "S9-05",
                        "Workspace upload resolution",
                        "PASS",
                        "file ID resolved",
                        t0=t0,
                    )
                else:
                    record(
                        sec,
                        "S9-05",
                        "Workspace upload resolution",
                        "WARN",
                        f"HTTP {r.status_code}",
                        t0=t0,
                    )
            except Exception as e:
                record(sec, "S9-05", "Workspace upload resolution", "FAIL", str(e)[:100], t0=t0)
            finally:
                with contextlib.suppress(Exception):
                    target.unlink()
    else:
        t0 = time.time()
        record(sec, "S9-05", "Workspace upload resolution", "INFO", "service not running", t0=t0)


OLLAMA_WORKSPACES = {
    "auto-security",
    "auto-redteam",
    "auto-blueteam",
    "auto-video",
    "auto-music",
}
