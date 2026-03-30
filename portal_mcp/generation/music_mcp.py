"""
Music Generation MCP Server
Wraps Meta AudioCraft/MusicGen for local music generation.
Exposes: generate_music, generate_continuation

Requires: pip install audiocraft
Models are downloaded automatically on first use from HuggingFace.
Start with: python -m mcp.generation.music_mcp
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("music-generation")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "music-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "generate_music",
        "description": "Generate music using Meta AudioCraft/MusicGen or Stable Audio",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the music to generate"},
                "duration": {"type": "number", "description": "Duration in seconds", "default": 10},
                "model": {
                    "type": "string",
                    "description": "Model size (small, medium, large, stable-audio)",
                    "default": "medium",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_continuation",
        "description": "Continue or extend a piece of music using a melody as input",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of how to continue the music",
                },
                "melody_path": {
                    "type": "string",
                    "description": "Path to a WAV/MP3 file to use as melodic conditioning",
                },
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds (max 30)",
                    "default": 10,
                },
                "model": {
                    "type": "string",
                    "description": "MusicGen model size — small | medium | large",
                    "default": "medium",
                },
            },
            "required": ["prompt", "melody_path"],
        },
    },
    {
        "name": "list_music_models",
        "description": "List available MusicGen model sizes and their requirements",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("GENERATED_FILES_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_MUSIC_FILES = int(os.getenv("MAX_MUSIC_FILES", "20"))


def _cleanup_old_music_files() -> None:
    """Keep only the MAX_MUSIC_FILES most recently generated music files."""
    import contextlib

    if not OUTPUT_DIR.exists():
        return
    music_files = sorted(
        OUTPUT_DIR.glob("music_*.wav"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,  # newest first
    )
    for old_file in music_files[MAX_MUSIC_FILES:]:
        with contextlib.suppress(OSError):
            old_file.unlink()
            logger.info("Cleaned up old music file: %s", old_file.name)


def _check_audiocraft() -> tuple[bool, str]:
    try:
        import audiocraft  # noqa: F401

        return True, ""
    except ImportError:
        return False, "AudioCraft not installed. Run: pip install audiocraft"


def _check_stable_audio() -> tuple[bool, str]:
    try:
        import stable_audio_tools  # noqa: F401

        return True, "stable-audio-tools available"
    except ImportError:
        return False, "stable-audio-tools not installed"


# Module-level MusicGen model cache — keyed by model size (small/medium/large).
# Avoids re-loading the model graph from disk on every call (P2).
_musicgen_cache: dict[str, Any] = {}  # type: ignore[valid-type]


def _get_musicgen_model(model_size: str) -> Any:  # type: ignore[type-arg]
    """Return cached MusicGen model for the given size, loading once per process (P2)."""
    if model_size not in _musicgen_cache:
        from audiocraft.models import MusicGen

        model_name = f"facebook/musicgen-{model_size}"
        logger.info("Loading MusicGen %s (first-time, cached for subsequent calls)", model_name)
        _musicgen_cache[model_size] = MusicGen.get_pretrained(model_name)
    return _musicgen_cache[model_size]


@mcp.tool()
async def generate_music(
    prompt: str,
    duration: float = 10.0,
    model_size: str = "medium",
    top_k: int = 250,
    temperature: float = 1.0,
    cfg_coef: float = 3.0,
) -> dict:
    """
    Generate music from a text description using Meta MusicGen or Stable Audio.

    Models are downloaded automatically on first use:
    - small: ~300MB (fast, lower quality)
    - medium: ~1.5GB (recommended, good quality)
    - large: ~3.3GB (best quality, needs 16GB+ VRAM or 32GB+ unified memory)
    - stable-audio: uses Stable Audio Open 1.0 (~3GB, higher quality)

    Args:
        prompt: Description of music to generate (e.g., "upbeat jazz piano solo", "dark orchestral")
        duration: Duration in seconds (default 10.0, max ~30s per generation)
        model_size: Model size — small, medium, large, or stable-audio (default medium)
        top_k: Top-k sampling parameter (default 250)
        temperature: Sampling temperature (default 1.0)
        cfg_coef: Classifier-free guidance strength (default 3.0; higher = closer to prompt)
    """
    # Handle stable-audio separately
    if model_size == "stable-audio":
        available, error = _check_stable_audio()
        if not available:
            return {
                "success": False,
                "error": f"stable-audio-tools not available: {error}. Use small/medium/large.",
            }
        result = await _generate_stable_audio(prompt, duration)
        if result.get("success"):
            _cleanup_old_music_files()
        return result

    available, error = _check_audiocraft()
    if not available:
        return {"success": False, "error": error}

    if model_size not in ("small", "medium", "large"):
        return {
            "success": False,
            "error": "model_size must be one of: small, medium, large, stable-audio",
        }

    result = await asyncio.to_thread(
        _generate_sync,
        prompt,
        duration,
        model_size,
        top_k,
        temperature,
        cfg_coef,
    )
    if result.get("success"):
        _cleanup_old_music_files()
    return result


def _generate_sync(
    prompt: str,
    duration: float,
    model_size: str,
    top_k: int,
    temperature: float,
    cfg_coef: float,
) -> dict:
    try:
        import torch
        import torchaudio

        model = _get_musicgen_model(model_size)
        model.set_generation_params(
            duration=duration,
            top_k=top_k,
            temperature=temperature,
            cfg_coef=cfg_coef,
        )

        model_name = f"facebook/musicgen-{model_size}"
        logger.info("Generating: %s", prompt[:80])
        with torch.no_grad():
            wav = model.generate([prompt])

        sample_rate = model.sample_rate
        audio_data = wav[0].cpu()

        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = OUTPUT_DIR / f"music_{safe_name}_{int(duration)}s.wav"
        torchaudio.save(str(output_file), audio_data, sample_rate)

        actual_duration = audio_data.shape[-1] / sample_rate
        return {
            "success": True,
            "path": str(output_file),
            "duration_seconds": round(actual_duration, 2),
            "sample_rate": sample_rate,
            "prompt": prompt,
            "model": model_name,
        }
    except Exception as e:
        logger.exception("Music generation failed")
        return {"success": False, "error": str(e)}


async def _generate_stable_audio(prompt: str, duration: float) -> dict:
    """Generate music using Stable Audio Open."""
    return await asyncio.to_thread(_stable_audio_sync, prompt, duration)


def _stable_audio_sync(prompt: str, duration: float) -> dict:
    """Synchronous Stable Audio generation."""
    try:
        import torch
        import torchaudio
        from stable_audio_tools import get_pretrained_model
        from stable_audio_tools.inference import generate

        logger.info("Loading Stable Audio Open model...")
        model, _ = get_pretrained_model("stabilityai/stable-audio-open-1.0")
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
        model = model.to(device)

        logger.info("Generating: %s", prompt[:80])
        # Generate audio
        output = generate(
            model=model,
            prompts=[prompt],
            duration=duration,
            cfg_scale=7.5,
            steps=50,
        )

        # Extract audio tensor
        audio = output["audio"][0]  # [channels, samples]
        if audio.shape[0] > 1:
            audio = audio.mean(dim=0)  # Mono

        sample_rate = 48000  # Stable Audio uses 48kHz
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = OUTPUT_DIR / f"music_{safe_name}_{int(duration)}s.wav"
        torchaudio.save(str(output_file), audio.unsqueeze(0), sample_rate)

        actual_duration = audio.shape[-1] / sample_rate
        return {
            "success": True,
            "path": str(output_file),
            "duration_seconds": round(actual_duration, 2),
            "sample_rate": sample_rate,
            "prompt": prompt,
            "model": "stabilityai/stable-audio-open-1.0",
        }
    except Exception as e:
        logger.exception("Stable Audio generation failed")
        return {"success": False, "error": str(e)}


def _generate_with_melody_sync(
    prompt: str,
    duration: float,
    model_size: str,
    melody_path: str,
    top_k: int,
    temperature: float,
    cfg_coef: float,
) -> dict:
    """Generate music with melody conditioning using AudioCraft."""
    try:
        import torch
        import torchaudio
        from audiocraft.models import MusicGen

        model_name = f"facebook/musicgen-{model_size}"
        logger.info("Loading MusicGen %s for melody continuation", model_name)
        model = MusicGen.get_pretrained(model_name)
        model.set_generation_params(
            duration=duration,
            top_k=top_k,
            temperature=temperature,
            cfg_coef=cfg_coef,
        )

        # Load and resample melody to match model's sample rate
        melody_waveform, sr = torchaudio.load(melody_path)
        if sr != model.sample_rate:
            melody_waveform = torchaudio.functional.resample(melody_waveform, sr, model.sample_rate)

        logger.info("Generating with melody: %s", prompt[:80])
        with torch.no_grad():
            wav = model.generate_with_chroma(
                [prompt], melody_waveform.unsqueeze(0), model.sample_rate
            )

        sample_rate = model.sample_rate
        audio_data = wav[0].cpu()

        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = OUTPUT_DIR / f"music_{safe_name}_{int(duration)}s.wav"
        torchaudio.save(str(output_file), audio_data, sample_rate)

        actual_duration = audio_data.shape[-1] / sample_rate
        return {
            "success": True,
            "path": str(output_file),
            "duration_seconds": round(actual_duration, 2),
            "sample_rate": sample_rate,
            "prompt": prompt,
            "model": model_name,
        }
    except Exception as e:
        logger.exception("Melody continuation failed")
        return {"success": False, "error": str(e)}


async def _run_music_generation(
    prompt: str,
    duration: float,
    model_name: str,
    melody_path: str | None = None,
) -> dict:
    """Run music generation, optionally with melody conditioning."""
    if melody_path:
        return await asyncio.to_thread(
            _generate_with_melody_sync,
            prompt,
            duration,
            model_name,
            melody_path,
            250,  # top_k default
            1.0,  # temperature default
            3.0,  # cfg_coef default
        )
    return await asyncio.to_thread(
        _generate_sync,
        prompt,
        duration,
        model_name,
        250,  # top_k default
        1.0,  # temperature default
        3.0,  # cfg_coef default
    )


@mcp.tool()
async def generate_continuation(
    prompt: str,
    melody_path: str,
    duration: int = 10,
    model: str = "medium",
) -> dict:
    """Continue or extend a piece of music using a melody as input.

    Args:
        prompt: Description of how to continue the music
        melody_path: Path to a WAV/MP3 file to use as melodic conditioning
        duration: Duration in seconds (max 30)
        model: MusicGen model size — small | medium | large
    """
    available, error = _check_audiocraft()
    if not available:
        return {"error": f"AudioCraft not available: {error}", "install": "pip install audiocraft"}

    from pathlib import Path as _Path

    if not _Path(melody_path).exists():
        return {"error": f"Melody file not found: {melody_path}"}

    result = await _run_music_generation(
        prompt=prompt, duration=duration, model_name=model, melody_path=melody_path
    )
    if result.get("success"):
        _cleanup_old_music_files()
    return result


@mcp.tool()
async def list_music_models() -> dict:
    """List available MusicGen model sizes and their requirements."""
    audiocraft_available, _ = _check_audiocraft()
    stable_audio_available, _ = _check_stable_audio()

    models = {
        "small": {"params": "300M", "vram_gb": 4, "quality": "fast"},
        "medium": {"params": "1.5B", "vram_gb": 8, "quality": "recommended"},
        "large": {"params": "3.3B", "vram_gb": 16, "quality": "best"},
    }

    if stable_audio_available:
        models["stable-audio"] = {
            "params": "~3GB",
            "vram_gb": 8,
            "quality": "high",
            "note": "Stable Audio Open 1.0",
        }

    return {
        "audiocraft_installed": audiocraft_available,
        "stable_audio_installed": stable_audio_available,
        "install_command": "pip install audiocraft stable-audio-tools"
        if not (audiocraft_available or stable_audio_available)
        else None,
        "models": models,
        "note": "Models are downloaded automatically from HuggingFace on first use.",
    }


if __name__ == "__main__":
    port = int(os.getenv("MUSIC_MCP_PORT", "8912"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
