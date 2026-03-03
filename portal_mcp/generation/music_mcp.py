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
        "description": "Generate music using Meta AudioCraft/MusicGen",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the music to generate"},
                "duration": {"type": "number", "description": "Duration in seconds", "default": 10},
                "model": {"type": "string", "description": "Model size (small, medium, large)", "default": "medium"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_continuation",
        "description": "Continue a melody pattern",
        "parameters": {
            "type": "object",
            "properties": {
                "melody": {"type": "string", "description": "Melody pattern as comma-separated note values"},
                "duration": {"type": "number", "description": "Duration in seconds", "default": 10},
            },
            "required": ["melody"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("GENERATED_FILES_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _check_audiocraft() -> tuple[bool, str]:
    try:
        import audiocraft  # noqa: F401

        return True, ""
    except ImportError:
        return False, "AudioCraft not installed. Run: pip install audiocraft"


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
    Generate music from a text description using Meta MusicGen.

    Models are downloaded automatically on first use:
    - small: ~300MB (fast, lower quality)
    - medium: ~1.5GB (recommended, good quality)
    - large: ~3.3GB (best quality, needs 16GB+ VRAM or 32GB+ unified memory)

    Args:
        prompt: Description of music to generate (e.g., "upbeat jazz piano solo", "dark orchestral")
        duration: Duration in seconds (default 10.0, max ~30s per generation)
        model_size: Model size — small, medium, or large (default medium)
        top_k: Top-k sampling parameter (default 250)
        temperature: Sampling temperature (default 1.0)
        cfg_coef: Classifier-free guidance strength (default 3.0; higher = closer to prompt)
    """
    available, error = _check_audiocraft()
    if not available:
        return {"success": False, "error": error}

    if model_size not in ("small", "medium", "large"):
        return {"success": False, "error": "model_size must be one of: small, medium, large"}

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        _generate_sync,
        prompt,
        duration,
        model_size,
        top_k,
        temperature,
        cfg_coef,
    )
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
        from audiocraft.models import MusicGen

        model_name = f"facebook/musicgen-{model_size}"
        logger.info("Loading MusicGen %s", model_name)
        model = MusicGen.get_pretrained(model_name)
        model.set_generation_params(
            duration=duration,
            top_k=top_k,
            temperature=temperature,
            cfg_coef=cfg_coef,
        )

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


@mcp.tool()
async def list_music_models() -> dict:
    """List available MusicGen model sizes and their requirements."""
    available, error = _check_audiocraft()
    return {
        "audiocraft_installed": available,
        "install_command": "pip install audiocraft" if not available else None,
        "models": {
            "small": {"params": "300M", "vram_gb": 4, "quality": "fast"},
            "medium": {"params": "1.5B", "vram_gb": 8, "quality": "recommended"},
            "large": {"params": "3.3B", "vram_gb": 16, "quality": "best"},
        },
        "note": "Models are downloaded automatically from HuggingFace on first use.",
    }


if __name__ == "__main__":
    port = int(os.getenv("MUSIC_MCP_PORT", "8912"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
