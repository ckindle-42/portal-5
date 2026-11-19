"""MiniMax-Music3-MLX MCP server for job-based local music generation."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
import os
import random
import signal
import sys
import wave
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from portal.modules.media.tools._admission import admit
from portal.modules.media.tools._jobs import (
    DEFAULT_STATUS_WAIT_S,
    STATUS_TOOL_TIMEOUT_S,
    MediaJobManager,
    start_reply,
)
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.owui_files import publish_file_sync
from portal.platform.mcp_host.workspace import get_generated_dir

port = int(os.getenv("MUSIC_MINIMAX_MCP_PORT", "8912"))
mcp = MCPServer("music-minimax")

# MCPServer.custom_route() has no return annotation upstream (mcp SDK), so mypy
# sees its decorator result as Any and flags every routed handler with
# untyped-decorator. Bind the concrete decorator type once so handlers keep
# their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

logger = logging.getLogger(__name__)
MODEL_DIR = Path(
    os.getenv("MUSIC_MINIMAX_MODEL_DIR", str(Path.home() / ".portal5" / "music-minimax" / "model"))
)
MAX_MUSIC_FILES = int(os.getenv("MAX_MUSIC_FILES", "20"))
MUSIC_IDLE_TIMEOUT_S = float(os.getenv("MUSIC_IDLE_TIMEOUT_S", "300"))
MUSIC_IDLE_EXIT = os.getenv("MUSIC_IDLE_EXIT", "0").lower() in ("1", "true", "yes")


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "music-minimax-mcp"})


def _cleanup_old_music_files() -> None:
    music_files = sorted(
        get_generated_dir("music").glob("music_*.wav"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
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


def _release_pipeline(*, exit_on_idle: bool | None = None) -> bool:
    """Release the in-process MLX pipeline after idle timeout."""
    global _pipeline_cache
    if _pipeline_cache is None:
        return False
    _pipeline_cache = None
    gc.collect()
    with contextlib.suppress(Exception):
        import mlx.core as mx

        clear_cache = getattr(mx, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()
        else:
            mx.metal.clear_cache()
    logger.info("Released MiniMax-Music3 pipeline after idle timeout")
    should_exit = MUSIC_IDLE_EXIT if exit_on_idle is None else exit_on_idle
    if should_exit:
        os.kill(os.getpid(), signal.SIGTERM)
    return True


_JOBS = MediaJobManager(idle_timeout_s=MUSIC_IDLE_TIMEOUT_S, on_idle=_release_pipeline)


def _generate_sync(
    job_id: str, prompt: str, lyrics: str, seconds: float, steps: int, seed: int, progress: Any
) -> dict[str, Any]:
    try:
        import numpy as np

        pipeline = _load_pipeline()
        from minimax_mlx_model import SAMPLE_RATE

        audio = pipeline.generate(prompt.strip(), lyrics.strip(), seconds, steps, seed, progress)
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in prompt[:40]).strip("_")
        output_file = get_generated_dir("music") / f"music_{safe_name}_{int(seconds)}s_{job_id}.wav"
        pcm = np.round(np.clip(audio.T, -1.0, 1.0) * 32_767).astype("<i2")
        with wave.open(str(output_file), "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm.tobytes())
        pub = publish_file_sync(output_file)
        if "error" in pub:
            return {"success": False, "error": pub["error"]}
        return {
            "success": True,
            "artifact_path": str(output_file),
            "filename": pub["filename"],
            "url": pub["url"],
            "download_url": pub["url"],
            "duration_seconds": round(seconds, 2),
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "prompt": prompt,
            "lyrics": lyrics,
            "seed": seed,
            "model": "MiniMax-Music3-MLX",
            "message": f"Music generated ({round(seconds, 1)}s). [Download WAV]({pub['url']})",
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
) -> dict[str, Any]:
    """Start a MiniMax full-song job; poll minimax_status with the returned job_id."""
    seconds = max(10.0, min(300.0, float(seconds)))
    steps = max(1, min(30, int(steps)))
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    if not _JOBS.is_busy:
        refusal = await admit("music:minimax3")
        if refusal:
            return refusal
    available, error = _check_minimax()
    if not available:
        return {"success": False, "error": error}

    job_ref: dict[str, str] = {}

    async def _run(progress: Any) -> dict[str, Any]:
        progress(0, "Checking memory before model load…")
        late_refusal = await admit("music:minimax3")
        if late_refusal:
            return late_refusal
        result = await asyncio.to_thread(
            _generate_sync,
            job_ref["id"],
            prompt,
            lyrics,
            seconds,
            steps,
            int(seed),
            progress,
        )
        if result.get("success"):
            _cleanup_old_music_files()
        return result

    job_id = _JOBS.start(_run, extra_fields={"seed": int(seed)})
    job_ref["id"] = job_id
    return start_reply(
        job_id,
        "minimax_status",
        f"duration={int(seconds)}s, steps={steps}",
        seed=seed,
    )


@mcp.tool()
async def music_start(
    prompt: str,
    lyrics: str = "[Instrumental]",
    seconds: float = 60.0,
    steps: int = 30,
    seed: int | None = None,
) -> dict[str, Any]:
    """Start an async music generation job; poll music_status with the returned job_id."""
    reply = await minimax_generate(
        prompt=prompt, lyrics=lyrics, seconds=seconds, steps=steps, seed=seed
    )
    if reply.get("success") and "job_id" in reply:
        reply["next_action"] = f"call music_status with job_id='{reply['job_id']}'"
    return reply


@mcp.tool(meta={"portal5/timeout_s": STATUS_TOOL_TIMEOUT_S})
async def minimax_status(job_id: str, wait_s: float = DEFAULT_STATUS_WAIT_S) -> dict[str, Any]:
    """Long-poll a MiniMax generation job up to wait_s seconds for progress or completion."""
    return await _JOBS.status(job_id, wait_s=wait_s)


@mcp.tool(meta={"portal5/timeout_s": STATUS_TOOL_TIMEOUT_S})
async def music_status(job_id: str, wait_s: float = DEFAULT_STATUS_WAIT_S) -> dict[str, Any]:
    """Long-poll a music generation job up to wait_s seconds for progress or completion."""
    return await _JOBS.status(job_id, wait_s=wait_s)


@mcp.tool()
async def minimax_models() -> dict[str, Any]:
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


bind_native_context(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
