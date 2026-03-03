"""
TTS MCP Server
Wraps Fish Speech or CosyVoice for local text-to-speech.
Exposes: speak, clone_voice, list_voices

Requires: Fish Speech (recommended) or CosyVoice
Start with: python -m mcp.generation.tts_mcp
"""

import asyncio
import logging
import os
from pathlib import Path

from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("tts-generation")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "tts-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "speak",
        "description": "Convert text to speech using Fish Speech or CosyVoice",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak"},
                "voice": {"type": "string", "description": "Voice name (e.g., female_zhang, male_yun)", "default": "female_zhang"},
                "backend": {"type": "string", "description": "TTS backend (fish_speech or cosyvoice)", "default": "fish_speech"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "clone_voice",
        "description": "Clone a voice from reference audio",
        "parameters": {
            "type": "object",
            "properties": {
                "reference_audio": {"type": "string", "description": "Path to reference audio file"},
                "text": {"type": "string", "description": "Text to speak with cloned voice"},
            },
            "required": ["reference_audio", "text"],
        },
    },
    {
        "name": "list_voices",
        "description": "List available TTS voices",
        "parameters": {"type": "object", "properties": {}},
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("GENERATED_FILES_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TTS_BACKEND = os.getenv("TTS_BACKEND", "fish_speech")  # "fish_speech" or "cosyvoice"

# Fish Speech voice presets
FISH_SPEECH_VOICES = {
    "female_zhang": "Female Chinese (Zhang)",
    "female_ning": "Female Chinese (Ning)",
    "male_yun": "Male Chinese (Yun)",
    "male_tian": "Male Chinese (Tian)",
    "english_alice": "English (Alice)",
    "english_marcus": "English (Marcus)",
    "japanese_yuki": "Japanese (Yuki)",
}

# CosyVoice voice presets (fallback)
COSYVOICE_SPEAKERS = {
    "中文女": "Chinese female",
    "中文男": "Chinese male",
    "英文女": "English female",
    "英文男": "English male",
    "日文女": "Japanese female",
    "日文男": "Japanese male",
}


def _check_fish_speech() -> tuple[bool, str]:
    """Check if Fish Speech is available."""
    try:
        import fish_speech  # noqa: F401
        return True, ""
    except ImportError:
        return False, "Fish Speech not installed. See: https://github.com/fishaudio/fish-speech"


def _check_cosyvoice() -> tuple[bool, str]:
    """Check if CosyVoice is available."""
    try:
        import cosyvoice  # noqa: F401
        import torchaudio  # noqa: F401
        return True, ""
    except ImportError:
        return False, "CosyVoice not installed. Run: pip install cosyvoice torchaudio"


@mcp.tool()
async def speak(
    text: str,
    voice: str = "female_zhang",
    speed: float = 1.0,
    output_format: str = "wav",
) -> dict:
    """
    Generate speech from text using Fish Speech (or CosyVoice fallback).

    Fish Speech is a modern TTS engine with high quality and MPS support.
    Runs efficiently on Apple Silicon M4.

    Args:
        text: Text to synthesize into speech
        voice: Voice preset (default: female_zhang)
        speed: Speech speed multiplier (default: 1.0, range 0.5-2.0)
        output_format: Audio format — wav or mp3 (default: wav)
    """
    if TTS_BACKEND == "cosyvoice":
        return await _speak_cosyvoice(text, voice, output_format)
    else:
        return await _speak_fish_speech(text, voice, speed, output_format)


async def _speak_fish_speech(
    text: str,
    voice: str,
    speed: float,
    output_format: str,
) -> dict:
    """Generate speech using Fish Speech."""
    available, error = _check_fish_speech()
    if not available:
        # Fall back to CosyVoice
        logger.warning("Fish Speech not available, falling back to CosyVoice")
        return await _speak_cosyvoice(text, voice, output_format)

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _fish_speech_sync,
            text,
            voice,
            speed,
            output_format,
        )
        return result
    except Exception as e:
        logger.exception("Fish Speech generation failed")
        return {"success": False, "error": str(e)}


def _fish_speech_sync(
    text: str,
    voice: str,
    speed: float,
    output_format: str,
) -> dict:
    """Synchronous Fish Speech generation."""
    try:
        from fish_speech.models import Text2Speech
        from fish_speech.utils import get_audio

        logger.info("Loading Fish Speech model...")
        tts = Text2Speech.load_from_checkpoint(
            checkpoint_path="models/fish_speech/fish-speech-1.4",
            device="mps",
        )

        logger.info("Generating speech for: %s", text[:50])
        audio = tts.generate(text, speaker_id=voice, speed=speed)

        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in text[:30]).strip("_")
        output_file = OUTPUT_DIR / f"tts_{safe_name}.{output_format}"

        # Save audio
        get_audio(audio).save(str(output_file))

        return {
            "success": True,
            "path": str(output_file),
            "format": output_format,
            "voice": voice,
            "speed": speed,
            "backend": "fish_speech",
        }
    except Exception as e:
        logger.error("Fish Speech generation failed: %s", e)
        return {"success": False, "error": str(e)}


async def _speak_cosyvoice(text: str, voice: str, output_format: str) -> dict:
    """Generate speech using CosyVoice (fallback)."""
    available, error = _check_cosyvoice()
    if not available:
        return {"success": False, "error": f"Neither Fish Speech nor CosyVoice available. Fish Speech: {error}"}

    valid_voices = list(COSYVOICE_SPEAKERS.keys())
    if voice not in valid_voices:
        voice = valid_voices[0]  # Default to first voice

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _cosyvoice_sync,
            text,
            voice,
            output_format,
        )
        return result
    except Exception as e:
        logger.exception("CosyVoice generation failed")
        return {"success": False, "error": str(e)}


def _cosyvoice_sync(text: str, voice: str, output_format: str) -> dict:
    """Synchronous CosyVoice generation."""
    try:
        import torchaudio
        from cosyvoice.cli.cosyvoice import CosyVoice

        output_file = OUTPUT_DIR / f"tts_{hash(text) % 10000}.wav"

        logger.info("Loading CosyVoice model...")
        cosyvoice = CosyVoice("pretrained_models/CosyVoice-300M-SFT")

        logger.info("Generating speech for: %s", text[:50])
        for output in cosyvoice.inference_sft(text, voice):
            torchaudio.save(str(output_file), output["tts_speech"], 22050)
            break

        if output_file.exists():
            return {
                "success": True,
                "path": str(output_file),
                "format": "wav",
                "voice": voice,
                "backend": "cosyvoice",
            }
        return {"success": False, "error": "Audio file not created"}

    except Exception as e:
        logger.error("CosyVoice generation failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
async def clone_voice(
    text: str,
    reference_audio_path: str,
) -> dict:
    """
    Clone voice from reference audio and generate speech.

    Uses zero-shot voice cloning (Fish Speech) or CosyVoice fallback.

    Args:
        text: Text to synthesize
        reference_audio_path: Path to reference audio file (5-30 seconds)
    """
    ref_path = Path(reference_audio_path)
    if not ref_path.exists():
        return {"success": False, "error": f"Reference audio not found: {reference_audio_path}"}

    if TTS_BACKEND == "cosyvoice" or TTS_BACKEND == "cosyvoice_fallback":
        return await _clone_cosyvoice(text, reference_audio_path)
    else:
        return await _clone_fish_speech(text, reference_audio_path)


async def _clone_fish_speech(text: str, reference_audio_path: str) -> dict:
    """Clone voice using Fish Speech."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _fish_clone_sync,
            text,
            reference_audio_path,
        )
        return result
    except Exception as e:
        logger.exception("Fish Speech voice cloning failed")
        # Fall back to CosyVoice
        return await _clone_cosyvoice(text, reference_audio_path)


def _fish_clone_sync(text: str, reference_audio_path: str) -> dict:
    """Synchronous Fish Speech voice cloning."""
    try:
        from fish_speech.models import Text2Speech
        from fish_speech.utils import get_audio, load_audio

        logger.info("Loading Fish Speech model for cloning...")
        tts = Text2Speech.load_from_checkpoint(
            checkpoint_path="models/fish_speech/fish-speech-1.4",
            device="mps",
        )

        # Load reference audio
        reference = load_audio(reference_audio_path, 32000)

        logger.info("Cloning voice and generating: %s", text[:50])
        audio = tts.generate(text, reference_audio=reference)

        safe_name = f"clone_{hash(text) % 10000}"
        output_file = OUTPUT_DIR / f"{safe_name}.wav"

        get_audio(audio).save(str(output_file))

        return {
            "success": True,
            "path": str(output_file),
            "format": "wav",
            "reference": reference_audio_path,
            "backend": "fish_speech",
        }
    except Exception as e:
        logger.error("Fish Speech cloning failed: %s", e)
        return {"success": False, "error": str(e)}


async def _clone_cosyvoice(text: str, reference_audio_path: str) -> dict:
    """Clone voice using CosyVoice."""
    available, error = _check_cosyvoice()
    if not available:
        return {"success": False, "error": f"Voice cloning requires CosyVoice: {error}"}

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            _cosyvoice_clone_sync,
            text,
            reference_audio_path,
        )
        return result
    except Exception as e:
        logger.exception("CosyVoice voice cloning failed")
        return {"success": False, "error": str(e)}


def _cosyvoice_clone_sync(text: str, reference_audio_path: str) -> dict:
    """Synchronous CosyVoice voice cloning."""
    try:
        import torchaudio
        from cosyvoice.cli.cosyvoice import CosyVoice

        output_file = OUTPUT_DIR / f"clone_{hash(text) % 10000}.wav"

        logger.info("Loading CosyVoice model for cloning...")
        cosyvoice = CosyVoice("pretrained_models/CosyVoice-300M-ZeroShot")

        # Load reference audio
        reference, sr = torchaudio.load(reference_audio_path)
        if sr != 22050:
            import torchaudio.functional as F
            reference = F.resample(reference, sr, 22050)

        logger.info("Cloning voice and generating: %s", text[:50])
        for output in cosyvoice.inference_zero_shot(text, reference, "中文女"):
            torchaudio.save(str(output_file), output["tts_speech"], 22050)
            break

        if output_file.exists():
            return {
                "success": True,
                "path": str(output_file),
                "format": "wav",
                "reference": reference_audio_path,
                "backend": "cosyvoice",
            }
        return {"success": False, "error": "Audio file not created"}

    except Exception as e:
        logger.error("CosyVoice cloning failed: %s", e)
        return {"success": False, "error": str(e)}


@mcp.tool()
async def list_voices() -> dict:
    """
    List available TTS voices.

    Returns voices for the configured backend (Fish Speech or CosyVoice).
    """
    if TTS_BACKEND == "cosyvoice":
        return {
            "backend": "cosyvoice",
            "voices": COSYVOICE_SPEAKERS,
        }
    else:
        # Check Fish Speech availability
        available, _ = _check_fish_speech()
        if available:
            return {
                "backend": "fish_speech",
                "voices": FISH_SPEECH_VOICES,
                "note": "Fish Speech requires models at models/fish_speech/",
            }
        else:
            # Show both with note
            return {
                "backend": "fish_speech_unavailable",
                "fish_speech": {
                    "available": False,
                    "voices": FISH_SPEECH_VOICES,
                    "install": "https://github.com/fishaudio/fish-speech",
                },
                "cosyvoice_fallback": {
                    "available": True,
                    "voices": COSYVOICE_SPEAKERS,
                },
                "current_backend": "cosyvoice (fallback active)",
            }


if __name__ == "__main__":
    port = int(os.getenv("TTS_MCP_PORT", "8916"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")