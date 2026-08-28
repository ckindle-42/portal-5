"""S8: Text-to-Speech tests."""

import time
from pathlib import Path

from tests.acceptance._common import (
    MCP,
    MLX_SPEECH_URL,
    _get,
    _get_acc_client,
    _wav_info,
    record,
)


async def _trainer_voice_roundtrip(sec: str) -> None:
    """S8-03/S8-04: register a trainer-voice profile, then speak with it (Chatterbox clone)."""
    ref = Path("tests/fixtures/audio/two_speaker_10s.wav")
    if not ref.exists():
        record(
            sec,
            "S8-03",
            "Register trainer voice",
            "INFO",
            "reference fixture missing",
            t0=time.time(),
        )
        return

    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.post(
            f"{MLX_SPEECH_URL}/v1/voices",
            json={
                "name": "acctest",
                "reference_audio": str(ref.resolve()),
                "reference_text": "the quick brown fox jumps over the lazy dog",
            },
            timeout=60,
        )
        ok = r.status_code == 200 and r.json().get("status") == "success"
        record(
            sec, "S8-03", "Register trainer voice", "PASS" if ok else "WARN", r.text[:120], t0=t0
        )
    except Exception as e:
        record(sec, "S8-03", "Register trainer voice", "FAIL", str(e)[:100], t0=t0)

    t0 = time.time()
    try:
        c = _get_acc_client()
        r = await c.post(
            f"{MLX_SPEECH_URL}/v1/audio/speech",
            json={"input": "Testing the trainer voice.", "voice": "trainer:acctest"},
            timeout=180,
        )
        if r.status_code == 200:
            info = _wav_info(r.content)
            ok = info and info["duration_s"] > 0.5
            record(
                sec,
                "S8-04",
                "Speak with trainer voice",
                "PASS" if ok else "WARN",
                f"duration: {info['duration_s']}s" if info else "no wav",
                t0=t0,
            )
        else:
            record(sec, "S8-04", "Speak with trainer voice", "FAIL", f"HTTP {r.status_code}", t0=t0)
    except Exception as e:
        record(sec, "S8-04", "Speak with trainer voice", "FAIL", str(e)[:100], t0=t0)


async def run() -> None:
    """S8: Text-to-Speech tests."""
    print("\n━━━ S8. TEXT-TO-SPEECH ━━━")
    sec = "S8"

    # S8-01: Check MLX Speech first (preferred on Apple Silicon)
    t0 = time.time()
    code, data = await _get(f"{MLX_SPEECH_URL}/health", timeout=5)
    mlx_speech_available = code == 200

    if mlx_speech_available:
        record(
            sec,
            "S8-01",
            "MLX Speech health",
            "PASS",
            f"voice_cloning: {data.get('voice_cloning', False)}",
            t0=t0,
        )

        # S8-02: TTS via MLX Speech
        t0 = time.time()
        try:
            c = _get_acc_client()
            r = await c.post(
                f"{MLX_SPEECH_URL}/v1/audio/speech",
                json={"input": "Hello from Portal 5 acceptance test.", "voice": "af_heart"},
                timeout=60,
            )
            if r.status_code == 200:
                wav_data = r.content
                info = _wav_info(wav_data)
                if info and info["duration_s"] > 0.5:
                    record(
                        sec,
                        "S8-02",
                        "MLX Speech TTS",
                        "PASS",
                        f"duration: {info['duration_s']}s",
                        t0=t0,
                    )
                else:
                    record(sec, "S8-02", "MLX Speech TTS", "WARN", f"invalid WAV: {info}", t0=t0)
            else:
                record(sec, "S8-02", "MLX Speech TTS", "FAIL", f"HTTP {r.status_code}", t0=t0)
        except Exception as e:
            record(sec, "S8-02", "MLX Speech TTS", "FAIL", str(e)[:100], t0=t0)

        await _trainer_voice_roundtrip(sec)
    else:
        record(
            sec,
            "S8-01",
            "MLX Speech health",
            "INFO",
            "not running (using Docker TTS fallback)",
            t0=t0,
        )

        # Fallback to Docker TTS
        t0 = time.time()
        code, data = await _get(f"http://localhost:{MCP['tts']}/health")
        record(
            sec,
            "S8-02",
            "Docker TTS health",
            "PASS" if code == 200 else "WARN",
            f"HTTP {code}",
            t0=t0,
        )
