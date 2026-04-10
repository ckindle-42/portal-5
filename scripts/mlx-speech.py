#!/usr/bin/env python3
"""
MLX Speech Server — Portal 5 (P5-FUT-012)

Host-native speech server for Apple Silicon using mlx-audio.
Replaces Docker-based kokoro-onnx TTS + faster-whisper ASR with:
  - Qwen3-TTS (voice cloning, emotion control, voice design, 10 languages)
  - Qwen3-ASR (MLX-native speech recognition)
  - Kokoro (backward-compatible voices via mlx-audio unified API)

Runs on the host (not Docker) — same pattern as mlx-proxy.py.
Open WebUI connects via host.docker.internal:8918.

Usage:
    python scripts/mlx-speech.py
    # or via launch.sh:
    ./launch.sh start-speech
"""

import asyncio
import contextlib
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mlx-speech")

# ── Configuration ──────────────────────────────────────────────────────────────

PORT = int(os.getenv("MLX_SPEECH_PORT", "8918"))
HOST = os.getenv("MLX_SPEECH_HOST", "0.0.0.0")

OUTPUT_DIR = Path(os.getenv("AI_OUTPUT_DIR", str(Path.home() / "AI_Output")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# TTS defaults
DEFAULT_TTS_BACKEND = os.getenv(
    "MLX_TTS_BACKEND", "kokoro"
)  # kokoro | qwen3_custom | qwen3_design | qwen3_base
DEFAULT_TTS_VOICE = os.getenv("MLX_TTS_VOICE", "af_heart")
DEFAULT_TTS_SPEED = float(os.getenv("MLX_TTS_SPEED", "1.0"))

# Model paths (auto-downloaded from HuggingFace on first use)
KOKORO_MODEL = os.getenv("MLX_KOKORO_MODEL", "mlx-community/Kokoro-82M-bf16")
QWEN3_TTS_CUSTOM_MODEL = os.getenv(
    "MLX_QWEN3_TTS_CUSTOM", "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit"
)
QWEN3_TTS_DESIGN_MODEL = os.getenv(
    "MLX_QWEN3_TTS_DESIGN", "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit"
)
QWEN3_TTS_BASE_MODEL = os.getenv(
    "MLX_QWEN3_TTS_BASE", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
)
QWEN3_ASR_MODEL = os.getenv("MLX_QWEN3_ASR", "mlx-community/Qwen3-ASR-1.7B-8bit")

# Qwen3-TTS preset speakers (CustomVoice model)
QWEN3_SPEAKERS = [
    "Chelsie",
    "Aiden",
    "Serena",
    "Vivian",
    "Ryan",
    "Nicole",
    "Aurora",
    "Luke",
    "Zara",
]

# ── Model Cache ────────────────────────────────────────────────────────────────

_tts_models: dict = {}  # keyed by model path
_asr_model = None

# Serialize TTS requests — concurrent Metal GPU command buffer encoding crashes
# AGXG16XFamilyCommandBuffer (macOS Apple Silicon). Semaphore(1) ensures one
# TTS generation at a time across all backends (Kokoro, Qwen3-TTS).
_tts_lock = asyncio.Semaphore(1)


def _get_tts_model(model_id: str):
    """Lazy-load and cache a TTS model."""
    if model_id not in _tts_models:
        from mlx_audio.tts.utils import load_model

        logger.info("Loading TTS model: %s", model_id)
        _tts_models[model_id] = load_model(model_id)
        logger.info("TTS model loaded: %s", model_id)
    return _tts_models[model_id]


def _get_asr_model():
    """Lazy-load and cache the ASR model."""
    global _asr_model
    if _asr_model is None:
        from mlx_audio.stt import load

        logger.info("Loading ASR model: %s", QWEN3_ASR_MODEL)
        _asr_model = load(QWEN3_ASR_MODEL)
        logger.info("ASR model loaded: %s", QWEN3_ASR_MODEL)
    return _asr_model


def _cleanup_stale_audio(max_age_hours: int = 1) -> None:
    """Remove speech audio files older than max_age_hours."""
    if not OUTPUT_DIR.exists():
        return
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for pattern in ("tts_*.wav", "clone_*.wav", "speech_*.wav"):
        for f in OUTPUT_DIR.glob(pattern):
            if f.stat().st_mtime < cutoff:
                with contextlib.suppress(OSError):
                    f.unlink()
                    removed += 1
    if removed:
        logger.info("Cleaned up %d stale audio files", removed)


# ── Determine backend from voice name ─────────────────────────────────────────

# Kokoro voices use format: {lang_prefix}_{name} (e.g., af_heart, bm_george)
KOKORO_VOICE_PREFIXES = {"af_", "am_", "bf_", "bm_", "jf_", "jm_", "zf_", "zm_"}


def _is_kokoro_voice(voice: str) -> bool:
    """Check if a voice name matches the Kokoro naming convention."""
    return any(voice.startswith(p) for p in KOKORO_VOICE_PREFIXES) or voice == "kokoro"


def _is_qwen3_speaker(voice: str) -> bool:
    """Check if a voice name is a Qwen3-TTS preset speaker."""
    return voice.capitalize() in QWEN3_SPEAKERS


# ── FastAPI App ────────────────────────────────────────────────────────────────

app = FastAPI(title="MLX Speech Server", version="1.0.0")


@app.get("/health")
async def health():
    backends = []
    try:
        import mlx_audio  # noqa: F401

        backends.append("mlx-audio")
    except ImportError:
        pass
    return {
        "status": "ok",
        "service": "mlx-speech",
        "port": PORT,
        "backends": backends,
        "tts_default_backend": DEFAULT_TTS_BACKEND,
        "tts_default_voice": DEFAULT_TTS_VOICE,
        "voice_cloning": True,
    }


# ── TTS: OpenAI-compatible /v1/audio/speech ────────────────────────────────────


@app.post("/v1/audio/speech")
async def openai_audio_speech(request: Request):
    """OpenAI-compatible TTS endpoint.

    Open WebUI sends: {"model": "...", "input": "text", "voice": "af_heart"}
    Returns audio/wav binary data.

    Voice routing:
    - Kokoro voices (af_heart, bm_george, etc.) → mlx-audio Kokoro backend
    - Qwen3 preset speakers (Chelsie, Ryan, etc.) → Qwen3-TTS CustomVoice
    - "design:<description>" → Qwen3-TTS VoiceDesign (creates voice from text)
    - "clone:<audio_path>" → Qwen3-TTS Base (voice cloning from reference audio)
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    text = body.get("input", body.get("text", ""))
    voice = body.get("voice", DEFAULT_TTS_VOICE)
    speed = float(body.get("speed", DEFAULT_TTS_SPEED))
    # Qwen3-TTS style instruction (optional, for CustomVoice)
    instruct = body.get("instruct", "")
    # Language for Qwen3-TTS (default English)
    language = body.get("language", "English")

    if not text:
        return JSONResponse({"error": "No input text provided"}, status_code=400)

    try:
        async with _tts_lock:
            result = await asyncio.to_thread(
                _generate_speech, text, voice, speed, instruct, language
            )
    except Exception as e:
        logger.error("TTS generation failed: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

    if "error" in result:
        return JSONResponse(result, status_code=503)

    audio_path = result.get("file_path", "")
    if not audio_path or not Path(audio_path).exists():
        return JSONResponse(
            {"error": "Audio file not generated"},
            status_code=503,
        )

    audio_bytes = Path(audio_path).read_bytes()

    # Clean up temp file after serving
    with contextlib.suppress(OSError):
        Path(audio_path).unlink()

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=speech.wav"},
    )


def _generate_speech(text: str, voice: str, speed: float, instruct: str, language: str) -> dict:
    """Route TTS request to appropriate backend. Runs in thread pool."""
    import soundfile as sf

    output_path = OUTPUT_DIR / f"speech_{uuid.uuid4().hex[:12]}.wav"

    try:
        # ── Route 1: Kokoro (backward-compatible, fast) ────────────────────
        if _is_kokoro_voice(voice):
            model = _get_tts_model(KOKORO_MODEL)
            # Kokoro uses lang_code prefix: a=American, b=British, j=Japanese, z=Chinese
            lang_code = voice[0] if len(voice) >= 2 and voice[1] == "f" or voice[1] == "m" else "a"
            audio_data = None
            for result in model.generate(text=text, voice=voice, speed=speed, lang_code=lang_code):
                audio_data = result.audio
            if audio_data is None:
                return {"error": "Kokoro generated no audio"}
            # mlx array → numpy for soundfile
            import numpy as np

            audio_np = np.array(audio_data, dtype=np.float32)
            sf.write(str(output_path), audio_np, 24000)
            return {
                "status": "success",
                "file_path": str(output_path),
                "backend": "kokoro",
                "voice": voice,
            }

        # ── Route 2: Qwen3-TTS VoiceDesign (voice from text description) ──
        if voice.startswith("design:"):
            description = voice[len("design:") :]
            model = _get_tts_model(QWEN3_TTS_DESIGN_MODEL)
            results = list(
                model.generate_voice_design(
                    text=text,
                    language=language,
                    instruct=description,
                )
            )
            if not results:
                return {"error": "VoiceDesign generated no audio"}
            import numpy as np

            audio_np = np.array(results[0].audio, dtype=np.float32)
            sf.write(str(output_path), audio_np, 24000)
            return {
                "status": "success",
                "file_path": str(output_path),
                "backend": "qwen3_design",
                "voice": voice,
            }

        # ── Route 3: Qwen3-TTS Base (voice cloning from reference audio) ──
        if voice.startswith("clone:"):
            ref_audio_path = voice[len("clone:") :]
            if not Path(ref_audio_path).exists():
                return {"error": f"Reference audio not found: {ref_audio_path}"}
            model = _get_tts_model(QWEN3_TTS_BASE_MODEL)
            results = list(
                model.generate(
                    text=text,
                    ref_audio=ref_audio_path,
                    ref_text="",  # Auto-transcribed if empty
                )
            )
            if not results:
                return {"error": "Voice cloning generated no audio"}
            import numpy as np

            audio_np = np.array(results[0].audio, dtype=np.float32)
            sf.write(str(output_path), audio_np, 24000)
            return {
                "status": "success",
                "file_path": str(output_path),
                "backend": "qwen3_base_clone",
                "voice": voice,
            }

        # ── Route 4: Qwen3-TTS CustomVoice (preset speakers + style) ──────
        # Default for unrecognized voice names — try as Qwen3 speaker
        speaker = voice.capitalize() if not _is_qwen3_speaker(voice) else voice.capitalize()
        if speaker not in QWEN3_SPEAKERS:
            # Fall back to first available Qwen3 speaker
            speaker = QWEN3_SPEAKERS[0]
            logger.warning("Unknown voice '%s', falling back to %s", voice, speaker)

        model = _get_tts_model(QWEN3_TTS_CUSTOM_MODEL)
        results = list(
            model.generate_custom_voice(
                text=text,
                speaker=speaker,
                language=language,
                instruct=instruct or "Natural and clear.",
            )
        )
        if not results:
            return {"error": "CustomVoice generated no audio"}
        import numpy as np

        audio_np = np.array(results[0].audio, dtype=np.float32)
        sf.write(str(output_path), audio_np, 24000)
        return {
            "status": "success",
            "file_path": str(output_path),
            "backend": "qwen3_custom",
            "voice": speaker,
            "instruct": instruct,
        }

    except Exception as e:
        logger.error("TTS generation error: %s", e, exc_info=True)
        return {"error": str(e)}


# ── STT: OpenAI-compatible /v1/audio/transcriptions ────────────────────────────


@app.post("/v1/audio/transcriptions")
async def openai_audio_transcriptions(
    file: UploadFile = File(...),  # noqa: B008
    language: str = Form(default="auto"),  # noqa: B008
    model: str = Form(default="qwen3-asr"),  # noqa: B008
):
    """OpenAI-compatible STT endpoint.

    Open WebUI sends multipart/form-data with 'file' field containing audio.
    """
    tmp_path = None
    try:
        contents = await file.read()
        suffix = ".wav"
        fname = file.filename or ""
        for ext in [".webm", ".ogg", ".mp4", ".m4a", ".wav", ".mp3"]:
            if fname.endswith(ext):
                suffix = ext
                break

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
    except Exception as e:
        return JSONResponse({"error": f"Upload failed: {e}"}, status_code=400)

    try:
        lang = language if language != "auto" else None
        result = await asyncio.to_thread(_transcribe, tmp_path, lang)
    except Exception as e:
        logger.error("ASR failed: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        with contextlib.suppress(Exception):
            if tmp_path:
                os.unlink(tmp_path)

    if "error" in result:
        return JSONResponse(result, status_code=500)

    return JSONResponse({"text": result.get("text", "")})


def _transcribe(file_path: str, language: str | None) -> dict:
    """Transcribe audio using Qwen3-ASR via mlx-audio. Runs in thread pool."""
    try:
        asr = _get_asr_model()
        kwargs = {"language": language} if language else {}
        result = asr.generate(file_path, **kwargs)
        return {
            "text": result.text,
            "backend": "qwen3_asr",
        }
    except Exception as e:
        logger.error("Qwen3-ASR error: %s", e)
        return {"error": str(e), "backend": "qwen3_asr"}


# ── Models endpoint ────────────────────────────────────────────────────────────


@app.get("/v1/models")
async def list_models():
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": "kokoro", "object": "model", "owned_by": "portal-5"},
                {"id": "qwen3-tts-custom", "object": "model", "owned_by": "portal-5"},
                {"id": "qwen3-tts-design", "object": "model", "owned_by": "portal-5"},
                {"id": "qwen3-tts-clone", "object": "model", "owned_by": "portal-5"},
                {"id": "qwen3-asr", "object": "model", "owned_by": "portal-5"},
            ],
        }
    )


# ── Voices endpoint (Portal 5 extension) ──────────────────────────────────────


@app.get("/v1/voices")
async def list_voices():
    return JSONResponse(
        {
            "kokoro": {
                "female_american": [
                    "af_heart",
                    "af_sky",
                    "af_bella",
                    "af_nicole",
                    "af_sarah",
                    "af_nova",
                ],
                "male_american": ["am_adam", "am_michael", "am_echo"],
                "female_british": ["bf_emma", "bf_isabella", "bf_alice"],
                "male_british": ["bm_george", "bm_lewis", "bm_daniel"],
                "japanese": ["jf_alpha", "jm_kumo"],
                "chinese": ["zf_xiaobei", "zm_yunxi"],
            },
            "qwen3_custom": {
                "speakers": QWEN3_SPEAKERS,
                "note": "Use speaker name as voice. Add 'instruct' field for style control.",
                "example_instructs": [
                    "Speak slowly and calmly.",
                    "Very excited and energetic.",
                    "Whisper softly.",
                    "Professional news anchor tone.",
                ],
            },
            "qwen3_design": {
                "note": "Use voice='design:<description>' to create a voice from text.",
                "examples": [
                    "design:A warm female voice with a slight British accent",
                    "design:A deep male voice, authoritative and calm",
                    "design:A cheerful young voice with high energy",
                ],
            },
            "qwen3_clone": {
                "note": "Use voice='clone:/path/to/reference.wav' to clone from 3-30s audio.",
            },
        }
    )


# ── Startup ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _cleanup_stale_audio()
    logger.info("MLX Speech Server starting on %s:%d", HOST, PORT)
    logger.info(
        "TTS backends: Kokoro (%s), Qwen3-TTS CustomVoice (%s), VoiceDesign (%s), Base/Clone (%s)",
        KOKORO_MODEL,
        QWEN3_TTS_CUSTOM_MODEL,
        QWEN3_TTS_DESIGN_MODEL,
        QWEN3_TTS_BASE_MODEL,
    )
    logger.info("ASR backend: Qwen3-ASR (%s)", QWEN3_ASR_MODEL)
    logger.info("Models load lazily on first request.")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
