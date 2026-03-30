"""
TTS MCP Server — Portal 5.0

Primary backend: kokoro-onnx (zero-setup, pip-installable, Apache 2.0)
Optional backend: fish-speech (higher quality voice cloning, manual install)

Kokoro models downloaded automatically on first use from HuggingFace (~200MB).
"""

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse, Response

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("tts-generation")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TTS_BACKEND = os.getenv("TTS_BACKEND", "kokoro")  # kokoro | fish_speech
TTS_VOICE = os.getenv("TTS_DEFAULT_VOICE", "af_heart")  # Kokoro default voice
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))


def _cleanup_stale_audio(max_age_hours: int = 1) -> None:
    """Remove TTS audio files older than max_age_hours. Called at startup."""
    if not OUTPUT_DIR.exists():
        return
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for f in OUTPUT_DIR.glob("tts_*.wav"):
        if f.stat().st_mtime < cutoff:
            with contextlib.suppress(OSError):
                f.unlink()
                removed += 1
    for f in OUTPUT_DIR.glob("clone_*.wav"):
        if f.stat().st_mtime < cutoff:
            with contextlib.suppress(OSError):
                f.unlink()
                removed += 1
    if removed:
        logger.info("Cleaned up %d stale TTS audio files", removed)


# Call at module load
_cleanup_stale_audio()

# Kokoro model cache location
KOKORO_CACHE_DIR = (
    Path(os.getenv("HF_HOME", str(Path.home() / ".cache" / "huggingface"))) / "kokoro"
)
KOKORO_MODEL_FILE = "kokoro-v1.0.onnx"
KOKORO_VOICES_FILE = "voices-v1.0.bin"
KOKORO_HF_REPO = "hexgrad/kokoro-onnx"

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro

# Module-level Kokoro model cache — avoids re-creating ONNX session per call (P2)
_kokoro_instance: "Kokoro | None" = None
# P6: skip Path.exists() stat calls after download is confirmed complete
_kokoro_models_checked: bool = False


def _get_kokoro() -> "Kokoro":
    """Return cached Kokoro ONNX session, creating it once per process (P2)."""
    global _kokoro_instance
    if _kokoro_instance is None:
        from kokoro_onnx import Kokoro

        model_path, voices_path = _ensure_kokoro_models()
        _kokoro_instance = Kokoro(model_path, voices_path)
    return _kokoro_instance


def _ensure_kokoro_models() -> tuple[str, str]:
    """Return (model_path, voices_path), downloading from HuggingFace if needed.

    ~60 MB total. Downloaded once, then cached at KOKORO_CACHE_DIR.
    After first download, _kokoro_models_checked flag prevents repeated stat() syscalls.
    """
    # P6: module-level flag — after download, skip all Path.exists() checks on hot path
    global _kokoro_models_checked
    if _kokoro_models_checked:
        return str(KOKORO_CACHE_DIR / KOKORO_MODEL_FILE), str(KOKORO_CACHE_DIR / KOKORO_VOICES_FILE)

    KOKORO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model_path = KOKORO_CACHE_DIR / KOKORO_MODEL_FILE
    voices_path = KOKORO_CACHE_DIR / KOKORO_VOICES_FILE

    if not model_path.exists() or not voices_path.exists():
        logger.info("Downloading kokoro-onnx model files (~60 MB)...")
        from huggingface_hub import hf_hub_download

        if not model_path.exists():
            hf_hub_download(
                repo_id=KOKORO_HF_REPO, filename=KOKORO_MODEL_FILE, local_dir=str(KOKORO_CACHE_DIR)
            )
        if not voices_path.exists():
            hf_hub_download(
                repo_id=KOKORO_HF_REPO, filename=KOKORO_VOICES_FILE, local_dir=str(KOKORO_CACHE_DIR)
            )
        logger.info("Kokoro model files ready at %s", KOKORO_CACHE_DIR)

    _kokoro_models_checked = True
    return str(model_path), str(voices_path)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    backend = _get_available_backend()
    return JSONResponse(
        {
            "status": "ok",
            "service": "tts-mcp",
            "backend": backend,
            "voice_cloning": _check_fish_speech()[0],
        }
    )


@mcp.custom_route("/v1/audio/speech", methods=["POST"])
async def openai_audio_speech(request):
    """OpenAI-compatible TTS endpoint.

    Open WebUI sends: {"model": "...", "input": "text", "voice": "af_heart"}
    We return audio/wav binary data.
    Required for AUDIO_TTS_ENGINE=openai integration.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    text = body.get("input", body.get("text", ""))
    voice = body.get("voice", TTS_VOICE)
    speed = float(body.get("speed", TTS_SPEED))

    if not text:
        return JSONResponse({"error": "No input text provided"}, status_code=400)

    # Use kokoro (primary zero-setup backend)
    available, error = _check_kokoro()
    if not available:
        return JSONResponse({"error": f"TTS unavailable: {error}"}, status_code=503)

    result = await _speak_kokoro(text, voice, speed)

    if "error" in result:
        # 503 = service unavailable (model not ready / downloading)
        return JSONResponse(result, status_code=503)

    # Read generated audio file and return as binary
    audio_path = result.get("file_path", "")
    if not audio_path or not Path(audio_path).exists():
        return JSONResponse(
            {"error": "Audio file not generated — TTS process produced no output"},
            status_code=503,
        )

    audio_bytes = Path(audio_path).read_bytes()

    # Clean up: the HTTP endpoint delivers bytes directly, no reason to keep the file
    with contextlib.suppress(OSError):
        Path(audio_path).unlink()

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=speech.wav"},
    )


@mcp.custom_route("/v1/models", methods=["GET"])
async def openai_models(request):
    """OpenAI-compatible models list for TTS voice selection."""
    kokoro_ok, _ = _check_kokoro()
    models = []
    if kokoro_ok:
        models = [
            {"id": "kokoro", "object": "model", "owned_by": "portal-5"},
        ]
    return JSONResponse({"object": "list", "data": models})


def _check_kokoro() -> tuple[bool, str]:
    try:
        import kokoro_onnx  # noqa: F401

        return True, "kokoro-onnx available"
    except ImportError:
        return False, "kokoro-onnx not installed. Run: pip install kokoro-onnx"


def _check_fish_speech() -> tuple[bool, str]:
    try:
        import fish_speech  # noqa: F401

        return True, "fish-speech available"
    except ImportError:
        return False, "fish-speech not installed (voice cloning unavailable)"


def _get_available_backend() -> str:
    if TTS_BACKEND == "fish_speech" and _check_fish_speech()[0]:
        return "fish_speech"
    if _check_kokoro()[0]:
        return "kokoro"
    return "none"


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "speak",
        "description": "Convert text to speech. Returns path to generated audio file.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to convert to speech"},
                "voice": {
                    "type": "string",
                    "description": "Voice name (kokoro: af_heart, af_sky, am_adam, bf_emma, bm_george)",
                    "default": "af_heart",
                },
                "speed": {
                    "type": "number",
                    "description": "Speech rate (0.5-2.0, default 1.0)",
                    "default": 1.0,
                },
                "backend": {
                    "type": "string",
                    "description": "Force specific backend: 'kokoro' or 'fish_speech'",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "clone_voice",
        "description": "Clone a voice from reference audio and speak text with it. Requires fish-speech to be installed.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_audio": {
                    "type": "string",
                    "description": "Path to 5-30 second reference audio file",
                },
                "text": {"type": "string", "description": "Text to speak with the cloned voice"},
            },
            "required": ["reference_audio", "text"],
        },
    },
    {
        "name": "list_voices",
        "description": "List available voices for text-to-speech.",
        "parameters": {"type": "object", "properties": {}},
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.tool()
async def speak(
    text: str,
    voice: str = "",
    speed: float = 1.0,
    backend: str = "",
) -> dict:
    """
    Convert text to speech. Returns path to generated audio file.

    Args:
        text: The text to convert to speech
        voice: Voice name (kokoro: af_heart, af_sky, am_adam, bf_emma, bm_george)
        speed: Speech rate (0.5-2.0, default 1.0)
        backend: Force specific backend: 'kokoro' or 'fish_speech'
    """
    use_backend = backend or TTS_BACKEND
    use_voice = voice or TTS_VOICE
    use_speed = speed or TTS_SPEED

    # Try kokoro first (zero-setup), fall back if explicitly requesting fish_speech
    if use_backend == "fish_speech":
        available, error = _check_fish_speech()
        if not available:
            return {
                "error": f"fish-speech not available: {error}. Using kokoro instead.",
                "suggestion": "Install fish-speech or use backend='kokoro'",
            }
        return await _speak_fish_speech(text, use_voice, use_speed)

    # Default: kokoro-onnx
    available, error = _check_kokoro()
    if not available:
        return {
            "error": f"kokoro-onnx not available: {error}",
            "install": "pip install kokoro-onnx",
        }

    return await _speak_kokoro(text, use_voice, use_speed)


async def _speak_kokoro(text: str, voice: str, speed: float) -> dict:
    """Generate speech using kokoro-onnx."""
    return await asyncio.to_thread(_kokoro_sync, text, voice, speed)


def _kokoro_sync(text: str, voice: str, speed: float) -> dict:
    """Generate speech using kokoro-onnx. Uses cached ONNX session (P2)."""
    try:
        import soundfile as sf

        kokoro = _get_kokoro()
        samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"tts_{hash(text) & 0xFFFFFF}.wav"
        sf.write(str(output_path), samples, sample_rate)

        return {
            "status": "success",
            "file_path": str(output_path),
            "backend": "kokoro",
            "voice": voice,
            "duration_estimate": f"{len(text) / 15:.1f}s",
        }
    except Exception as e:
        logger.error("Kokoro TTS error: %s", e)
        return {"error": str(e), "backend": "kokoro"}


async def _speak_fish_speech(text: str, voice: str, speed: float) -> dict:
    """Generate speech using fish-speech."""
    return await asyncio.to_thread(_fish_speech_sync, text, voice, speed)


def _fish_speech_sync(text: str, voice: str, speed: float) -> dict:
    try:
        import torch
        from fish_speech.models import Text2Speech
        from fish_speech.utils import get_audio

        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
        logger.info("Loading Fish Speech model on %s...", device)
        tts = Text2Speech.load_from_checkpoint(
            checkpoint_path="models/fish_speech/fish-speech-1.4",
            device=device,
        )

        logger.info("Generating speech for: %s", text[:50])
        audio = tts.generate(text, speaker_id=voice, speed=speed)

        output_path = OUTPUT_DIR / f"tts_{hash(text) & 0xFFFFFF}.wav"
        get_audio(audio).save(str(output_path))

        return {
            "status": "success",
            "file_path": str(output_path),
            "backend": "fish_speech",
            "voice": voice,
        }
    except Exception as e:
        logger.error("Fish Speech generation failed: %s", e)
        return {"error": str(e), "backend": "fish_speech"}


@mcp.tool()
async def clone_voice(
    reference_audio: str,
    text: str,
) -> dict:
    """
    Clone a voice from reference audio and speak text with it.
    Requires fish-speech to be installed (advanced feature).

    Args:
        reference_audio: Path to 5-30 second reference audio file
        text: Text to speak with the cloned voice
    """
    available, error = _check_fish_speech()
    if not available:
        return {
            "error": "Voice cloning requires fish-speech",
            "status": "unavailable",
            "install_docs": "See docs/FISH_SPEECH_SETUP.md",
            "alternative": "Use speak() tool with built-in kokoro voices",
        }
    return await _clone_fish_speech(text, reference_audio)


async def _clone_fish_speech(text: str, reference_audio_path: str) -> dict:
    return await asyncio.to_thread(_fish_clone_sync, text, reference_audio_path)


def _fish_clone_sync(text: str, reference_audio_path: str) -> dict:
    try:
        from fish_speech.models import Text2Speech
        from fish_speech.utils import get_audio, load_audio

        model = Text2Speech.from_pretrained(
            "models/fish_speech/fish-speech-1.4",
            device="mps",
        )
        ref_audio, ref_sr = load_audio(reference_audio_path)
        audio = get_audio(model, text, reference=ref_audio)

        output_path = OUTPUT_DIR / f"clone_{hash(text) & 0xFFFFFF}.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        import soundfile as sf

        sf.write(str(output_path), audio, 24000)
        return {"status": "success", "file_path": str(output_path), "backend": "fish_speech"}
    except Exception as e:
        return {"error": str(e), "backend": "fish_speech"}


@mcp.tool()
async def list_voices() -> dict:
    """List available voices for text-to-speech."""
    kokoro_available, _ = _check_kokoro()
    fish_available, _ = _check_fish_speech()

    voices = {}
    if kokoro_available:
        voices["kokoro"] = {
            "female_american": ["af_heart", "af_sky", "af_bella", "af_nicole", "af_sarah"],
            "male_american": ["am_adam", "am_michael"],
            "female_british": ["bf_emma", "bf_isabella"],
            "male_british": ["bm_george", "bm_lewis"],
        }
    if fish_available:
        voices["fish_speech"] = ["female_zhang", "male_yun", "custom (from reference audio)"]

    return {
        "available_backends": list(voices.keys()),
        "voices": voices,
        "default_backend": _get_available_backend(),
        "default_voice": TTS_VOICE,
        "voice_cloning": fish_available,
    }


if __name__ == "__main__":
    port = int(os.getenv("TTS_MCP_PORT", "8916"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
