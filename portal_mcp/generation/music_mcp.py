"""
Music Generation MCP Server
Wraps HuggingFace MusicGen (facebook/musicgen-*) for local music generation.
Exposes: generate_music, generate_continuation, list_music_models

Uses the `transformers` library instead of AudioCraft — same models, same quality,
works on aarch64 Linux (Docker on Apple Silicon), macOS MPS, and CUDA.
AudioCraft is NOT used: its torchtext/xformers dependencies have no aarch64 wheels.

Models are downloaded automatically on first use from HuggingFace (via HF_HOME).
Start with: python -m portal_mcp.generation.music_mcp
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from starlette.responses import FileResponse, JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

port = int(os.getenv("MUSIC_MCP_PORT", "8912"))
mcp = FastMCP("music-generation", host="0.0.0.0")

SAFE_FILENAME = re.compile(r"^[\w\-\.\s]+$")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "music-mcp"})


@mcp.custom_route("/files/{filename:path}", methods=["GET"])
async def serve_generated_file(request):
    """Serve generated audio files for browser download."""
    filename = request.path_params["filename"]
    if not SAFE_FILENAME.match(filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = OUTPUT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="audio/wav",
    )


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "generate_music",
        "description": "Generate music using HuggingFace MusicGen (facebook/musicgen-*)",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the music to generate"},
                "duration": {
                    "type": "number",
                    "description": "Duration in seconds (5-30)",
                    "default": 10,
                },
                "model": {
                    "type": "string",
                    "description": "Model size: small (~300MB), medium (~1.5GB), large (~3.3GB, default)",
                    "default": "large",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_continuation",
        "description": "Continue or extend a piece of music using a melody WAV as input",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of how to continue the music",
                },
                "melody_path": {
                    "type": "string",
                    "description": "Path to a WAV file to use as melodic conditioning",
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

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/generated"))
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
        reverse=True,
    )
    for old_file in music_files[MAX_MUSIC_FILES:]:
        with contextlib.suppress(OSError):
            old_file.unlink()
            logger.info("Cleaned up old music file: %s", old_file.name)


def _check_musicgen() -> tuple[bool, str]:
    """Check that transformers, torch, and scipy are importable."""
    missing = []
    for pkg in ("transformers", "torch", "scipy"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        return False, f"Missing: {', '.join(missing)}. Run: pip install torch transformers scipy"
    return True, ""


def _get_device() -> str:
    """Select best available torch device: MPS → CUDA → CPU."""
    try:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


# Module-level cache: model_size → (processor, model)
# Loaded once per process, kept in memory for subsequent calls.
_musicgen_cache: dict[str, tuple[Any, Any]] = {}


def _load_musicgen(model_size: str) -> tuple[Any, Any]:
    """Return cached (processor, model) for the given size, loading once per process."""
    if model_size not in _musicgen_cache:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        model_name = f"facebook/musicgen-{model_size}"
        logger.info(
            "Loading MusicGen %s (first-time load, cached for subsequent calls)", model_name
        )
        processor = AutoProcessor.from_pretrained(model_name)
        model = MusicgenForConditionalGeneration.from_pretrained(model_name)
        device = _get_device()
        logger.info("MusicGen using device: %s", device)
        model = model.to(device)
        _musicgen_cache[model_size] = (processor, model)
        logger.info("MusicGen %s loaded successfully", model_name)
    return _musicgen_cache[model_size]


def _tokens_for_duration(duration: float) -> int:
    """MusicGen generates audio tokens at 50 Hz — convert seconds to token count."""
    return int(duration * 50)


def _generate_sync(
    prompt: str,
    duration: float,
    model_size: str,
    top_k: int,
    temperature: float,
    guidance_scale: float,
) -> dict:
    """Synchronous MusicGen generation via transformers."""
    try:
        import numpy as np
        import scipy.io.wavfile as wavfile
        import torch

        processor, model = _load_musicgen(model_size)
        device = next(model.parameters()).device

        inputs = processor(text=[prompt], padding=True, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}

        max_new_tokens = _tokens_for_duration(duration)
        logger.info("Generating %.1fs of music: %s", duration, prompt[:80])

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "guidance_scale": guidance_scale,
        }
        if temperature != 1.0 or top_k != 250:
            gen_kwargs["do_sample"] = True
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_k"] = top_k

        with torch.no_grad():
            audio_values = model.generate(**inputs, **gen_kwargs)

        sampling_rate = model.config.audio_encoder.sampling_rate  # 32000 Hz
        audio_data = audio_values[0, 0].cpu().float().numpy()

        # Normalize and convert to int16 for WAV
        peak = np.abs(audio_data).max()
        if peak > 0:
            audio_data = audio_data / peak
        audio_int16 = (audio_data * 32767).astype(np.int16)

        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = OUTPUT_DIR / f"music_{safe_name}_{int(duration)}s.wav"
        wavfile.write(str(output_file), sampling_rate, audio_int16)

        actual_duration = len(audio_data) / sampling_rate
        download_url = f"http://localhost:{port}/files/{output_file.name}"
        return {
            "success": True,
            "filename": output_file.name,
            "download_url": download_url,
            "duration_seconds": round(actual_duration, 2),
            "sample_rate": sampling_rate,
            "prompt": prompt,
            "model": f"facebook/musicgen-{model_size}",
            "device": str(device),
        }
    except Exception as e:
        logger.exception("Music generation failed")
        return {"success": False, "error": str(e)}


def _generate_with_melody_sync(
    prompt: str,
    duration: float,
    model_size: str,
    melody_path: str,
    top_k: int,
    temperature: float,
    guidance_scale: float,
) -> dict:
    """Synchronous MusicGen melody-conditioned generation via transformers."""
    try:
        import numpy as np
        import scipy.io.wavfile as wavfile
        import torch
        import torchaudio

        processor, model = _load_musicgen(model_size)
        device = next(model.parameters()).device

        # Load melody and resample to processor's expected rate (32000 Hz)
        waveform, sr = torchaudio.load(melody_path)
        target_sr = processor.feature_extractor.sampling_rate
        if sr != target_sr:
            waveform = torchaudio.functional.resample(waveform, sr, target_sr)
        # Mix to mono if stereo
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        melody_np = waveform.numpy()

        inputs = processor(
            audio=melody_np,
            sampling_rate=target_sr,
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        max_new_tokens = _tokens_for_duration(duration)
        logger.info("Generating %.1fs with melody conditioning: %s", duration, prompt[:80])

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "guidance_scale": guidance_scale,
        }
        if temperature != 1.0 or top_k != 250:
            gen_kwargs["do_sample"] = True
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_k"] = top_k

        with torch.no_grad():
            audio_values = model.generate(**inputs, **gen_kwargs)

        sampling_rate = model.config.audio_encoder.sampling_rate
        audio_data = audio_values[0, 0].cpu().float().numpy()

        peak = np.abs(audio_data).max()
        if peak > 0:
            audio_data = audio_data / peak
        audio_int16 = (audio_data * 32767).astype(np.int16)

        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = OUTPUT_DIR / f"music_{safe_name}_{int(duration)}s.wav"
        wavfile.write(str(output_file), sampling_rate, audio_int16)

        actual_duration = len(audio_data) / sampling_rate
        download_url = f"http://localhost:{port}/files/{output_file.name}"
        return {
            "success": True,
            "filename": output_file.name,
            "download_url": download_url,
            "duration_seconds": round(actual_duration, 2),
            "sample_rate": sampling_rate,
            "prompt": prompt,
            "model": f"facebook/musicgen-{model_size}",
            "device": str(device),
        }
    except Exception as e:
        logger.exception("Melody continuation failed")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def generate_music(
    prompt: str,
    duration: float = 10.0,
    model_size: str = "large",
    top_k: int = 250,
    temperature: float = 1.0,
    cfg_coef: float = 3.0,
) -> dict:
    """
    Generate music from a text description using HuggingFace MusicGen.

    Models are downloaded from HuggingFace on first use (cached in HF_HOME):
    - small:  ~300MB  — fast, lower quality, good for quick tests
    - medium: ~1.5GB  — good quality
    - large:  ~3.3GB  — best quality (default)

    Device priority: MPS (Apple Silicon) → CUDA → CPU.
    On CPU (Docker/aarch64): ~3-5x realtime (10s clip takes ~30-50s).

    Args:
        prompt:      Description of the music (e.g. "upbeat jazz piano solo")
        duration:    Duration in seconds (5–30, default 10)
        model_size:  small | medium | large (default medium)
        top_k:       Top-k sampling (default 250; lower = more focused)
        temperature: Sampling temperature (default 1.0; lower = more conservative)
        cfg_coef:    Classifier-free guidance scale (default 3.0; higher = more prompt-faithful)
    """
    duration = max(5.0, min(30.0, float(duration)))

    if model_size not in ("small", "medium", "large"):
        return {"success": False, "error": "model_size must be: small, medium, or large"}

    available, error = _check_musicgen()
    if not available:
        return {"success": False, "error": error}

    result = await asyncio.to_thread(
        _generate_sync, prompt, duration, model_size, top_k, temperature, cfg_coef
    )
    if result.get("success"):
        _cleanup_old_music_files()
    return result


@mcp.tool()
async def generate_continuation(
    prompt: str,
    melody_path: str,
    duration: int = 10,
    model: str = "medium",
) -> dict:
    """Continue or extend a piece of music using a melody WAV as input.

    Args:
        prompt:      Description of how to continue the music
        melody_path: Path to a WAV file to use as melodic conditioning
        duration:    Duration in seconds (max 30)
        model:       MusicGen model size — small | medium | large
    """
    available, error = _check_musicgen()
    if not available:
        return {"error": f"MusicGen not available: {error}"}

    melody = Path(melody_path).resolve()
    allowed = OUTPUT_DIR.resolve()
    if not str(melody).startswith(str(allowed) + os.sep):
        return {"error": "melody_path must be within the output directory"}
    if not melody.exists():
        return {"error": f"Melody file not found: {melody_path}"}

    result = await asyncio.to_thread(
        _generate_with_melody_sync,
        prompt,
        float(duration),
        model,
        str(melody),
        250,
        1.0,
        3.0,
    )
    if result.get("success"):
        _cleanup_old_music_files()
    return result


@mcp.tool()
async def list_music_models() -> dict:
    """List available MusicGen model sizes and their requirements."""
    available, err = _check_musicgen()
    device = _get_device() if available else "unavailable"

    return {
        "backend": "HuggingFace transformers (MusicGen)",
        "available": available,
        "error": err if not available else None,
        "device": device,
        "models": {
            "small": {"params": "300M", "ram_gb": 2, "quality": "fast"},
            "medium": {"params": "1.5B", "ram_gb": 6, "quality": "recommended"},
            "large": {"params": "3.3B", "ram_gb": 12, "quality": "best"},
        },
        "note": (
            "Models auto-download from HuggingFace on first use. "
            "CPU inference: ~3-5x realtime (10s clip ≈ 30-50s on Docker/aarch64). "
            "MPS inference: ~1-2x realtime on Apple Silicon."
        ),
    }


if __name__ == "__main__":
    port = int(os.getenv("MUSIC_MCP_PORT", "8912"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
