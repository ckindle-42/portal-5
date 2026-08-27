"""MiniMax-Music3-MLX MCP server for job-based local music generation."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import sys
import time
import uuid
import wave
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from starlette.responses import FileResponse, JSONResponse

from portal.modules.media.tools._admission import admit
from portal.platform.data_loader import load_data

port = int(os.getenv("MUSIC_MINIMAX_MCP_PORT", "8912"))
mcp = MCPServer("music-minimax")
PUBLIC_URL = os.getenv("MUSIC_PUBLIC_URL", f"http://localhost:{port}/files/music").rstrip("/")
SAFE_FILENAME = re.compile(r"^[\w\-\.\s]+$")
logger = logging.getLogger(__name__)
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR = Path(
    os.getenv("MUSIC_MINIMAX_MODEL_DIR", str(Path.home() / ".portal5" / "music-minimax" / "model"))
)
MAX_MUSIC_FILES = int(os.getenv("MAX_MUSIC_FILES", "20"))
MAX_JOB_RECORDS = 50


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "music-minimax-mcp"})


@mcp.custom_route("/files/music/{filename:path}", methods=["GET"])
async def serve_generated_file(request):
    filename = request.path_params["filename"]
    if not SAFE_FILENAME.match(filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    file_path = OUTPUT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path=str(file_path), filename=filename, media_type="audio/wav")


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_music_minimax_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


@mcp.custom_route("/tools/minimax_generate", methods=["POST"])
async def minimax_generate_endpoint(request):
    args = (await request.json()).get("arguments", {})
    return JSONResponse(
        await minimax_generate(
            prompt=args.get("prompt", ""),
            lyrics=args.get("lyrics", "[Instrumental]"),
            seconds=float(args.get("seconds", 60.0)),
            steps=int(args.get("steps", 30)),
            seed=args.get("seed"),
        )
    )


@mcp.custom_route("/tools/minimax_status", methods=["POST"])
async def minimax_status_endpoint(request):
    args = (await request.json()).get("arguments", {})
    return JSONResponse(await minimax_status(job_id=args.get("job_id", "")))


@mcp.custom_route("/tools/minimax_models", methods=["POST"])
async def minimax_models_endpoint(request):
    return JSONResponse(await minimax_models())


def _cleanup_old_music_files() -> None:
    import contextlib

    music_files = sorted(
        OUTPUT_DIR.glob("music_*.wav"), key=lambda f: f.stat().st_mtime, reverse=True
    )
    for old_file in music_files[MAX_MUSIC_FILES:]:
        with contextlib.suppress(OSError):
            old_file.unlink()


def _check_minimax() -> tuple[bool, str]:
    try:
        import mlx.core  # noqa: F401
    except ImportError:
        return False, "mlx not installed. Run: pip install mlx==0.30.6 mlx-metal==0.30.6"
    if not (MODEL_DIR / "minimax_mlx_model.py").exists():
        return (
            False,
            f"Model not found at {MODEL_DIR}. Run: ./launch.sh install-music-minimax to download PocketAiHub/MiniMax-Music3-MLX (~11.9GB).",
        )
    return True, ""


_pipeline_cache: Any | None = None


def _load_pipeline() -> Any:
    global _pipeline_cache
    if _pipeline_cache is None:
        if str(MODEL_DIR) not in sys.path:
            sys.path.insert(0, str(MODEL_DIR))
        from minimax_mlx_model import MiniMaxMusic3MlxPipeline  # type: ignore[import-not-found]

        _pipeline_cache = MiniMaxMusic3MlxPipeline(
            MODEL_DIR, lambda stage, msg: logger.info("[load %s/5] %s", stage, msg)
        )
    return _pipeline_cache


_JOBS: dict[str, dict[str, Any]] = {}
_JOB_ORDER: list[str] = []


def _record_job(job_id: str, **fields: Any) -> None:
    _JOBS.setdefault(job_id, {}).update(fields)


def _new_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    _JOB_ORDER.append(job_id)
    while len(_JOB_ORDER) > MAX_JOB_RECORDS:
        _JOBS.pop(_JOB_ORDER.pop(0), None)
    return job_id


async def _run_job(
    job_id: str, prompt: str, lyrics: str, seconds: float, steps: int, seed: int
) -> None:
    _record_job(job_id, status="running", stage=0, message="Starting…", started_at=time.time())

    def progress(stage: int, message: str) -> None:
        _record_job(job_id, stage=stage, message=message)

    try:
        result = await asyncio.to_thread(
            _generate_sync, job_id, prompt, lyrics, seconds, steps, seed, progress
        )
        if result.get("success"):
            _record_job(job_id, status="done", **result, finished_at=time.time())
            _cleanup_old_music_files()
        else:
            _record_job(
                job_id,
                status="error",
                error=result.get("error", "unknown error"),
                finished_at=time.time(),
            )
    except Exception as exc:
        logger.exception("MiniMax job %s failed", job_id)
        _record_job(job_id, status="error", error=str(exc), finished_at=time.time())


def _generate_sync(
    job_id: str, prompt: str, lyrics: str, seconds: float, steps: int, seed: int, progress: Any
) -> dict:
    try:
        import numpy as np

        pipeline = _load_pipeline()
        from minimax_mlx_model import SAMPLE_RATE  # type: ignore[import-not-found]

        audio = pipeline.generate(prompt.strip(), lyrics.strip(), seconds, steps, seed, progress)
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = OUTPUT_DIR / f"music_{safe_name}_{int(seconds)}s_{job_id}.wav"
        pcm = np.round(np.clip(audio.T, -1.0, 1.0) * 32_767).astype("<i2")
        with wave.open(str(output_file), "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm.tobytes())
        download_url = f"{PUBLIC_URL}/{output_file.name}"
        return {
            "success": True,
            "filename": output_file.name,
            "download_url": download_url,
            "duration_seconds": round(seconds, 2),
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "prompt": prompt,
            "lyrics": lyrics,
            "seed": seed,
            "model": "MiniMax-Music3-MLX",
            "message": f"Music generated ({round(seconds, 1)}s). [Download WAV]({download_url})",
        }
    except Exception as exc:
        logger.exception("MiniMax generation failed")
        return {"success": False, "error": str(exc)}


@mcp.tool()
async def minimax_generate(
    prompt: str,
    lyrics: str = "[Instrumental]",
    seconds: float = 60.0,
    steps: int = 30,
    seed: int | None = None,
) -> dict:
    """Start a MiniMax full-song job; poll minimax_status with the returned job_id."""
    seconds = max(10.0, min(300.0, float(seconds)))
    steps = max(1, min(30, int(steps)))
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    refusal = await admit("music:minimax3")
    if refusal:
        return refusal
    available, error = _check_minimax()
    if not available:
        return {"success": False, "error": error}
    job_id = _new_job()
    asyncio.create_task(_run_job(job_id, prompt, lyrics, seconds, steps, int(seed)))
    return {
        "success": True,
        "job_id": job_id,
        "seed": seed,
        "message": f"Generation started (job {job_id}). Poll minimax_status to check progress.",
    }


@mcp.tool()
async def minimax_status(job_id: str) -> dict:
    """Check a MiniMax generation job."""
    job = _JOBS.get(job_id)
    return (
        {"status": "unknown", "job_id": job_id, "message": "No such job (or it aged out)."}
        if job is None
        else {"job_id": job_id, **job}
    )


@mcp.tool()
async def minimax_models() -> dict:
    """List MiniMax capabilities and availability."""
    available, err = _check_minimax()
    return {
        "backend": "MiniMax-Music3-MLX (native MLX, Apple Silicon only)",
        "available": available,
        "error": err if not available else None,
        "models": {
            "minimax-music3": {
                "disk_gb": 11.9,
                "duration_range_s": [10, 300],
                "steps_range": [1, 30],
                "output": "44.1kHz 16-bit stereo WAV",
                "supports_lyrics_vocals": True,
            }
        },
        "note": "Job-based (minimax_generate + minimax_status). Apple Silicon only, no fallback. Complete-quality default is 60s / 30 steps.",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
