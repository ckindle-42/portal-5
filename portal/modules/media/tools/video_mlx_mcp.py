"""Video-MLX MCP — MLX-native local video generation (Apple Silicon).

Headless wrapper over the ``ltx-2-mlx`` CLI (pure-MLX LTX-2 port) running the
LTX-2.5 packs, with an opt-in ``mlx-video`` Wan2.2-TI2V-5B fallback. Runs on
the host MLX layer (like mflux / mlx-transcribe), NOT in any Docker image.

The tool surface is the shared media async pattern: ``video_start`` submits a
job and returns its id immediately, ``video_status`` long-polls it (so the
Pipeline's 20-hop tool loop covers a multi-minute render), and
``video_models`` lists the roster. Memory: the Tier-1 admission check
(``admit``) reclaims idle LLM residents through the Pipeline before a load,
and the per-job subprocess exiting releases Metal memory after one — the
renderer is never kept resident between jobs.

Port 8935 (``VIDEO_MLX_MCP_PORT``). Apple Silicon only; there is no CPU/CUDA
fallback for this engine. Output is preview-grade and practically capped at
~4-6s clips on this hardware.
"""

from __future__ import annotations

import asyncio
import os
import uuid
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
from portal.platform.mcp_host import assert_public_http_url, resolve_upload_path
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import get_generated_dir

port = int(os.getenv("VIDEO_MLX_MCP_PORT", "8935"))
mcp = MCPServer("video-mlx-generation")

# MCPServer.custom_route() has no return annotation upstream (mcp SDK), so mypy
# sees its decorator result as Any and flags every routed handler with
# untyped-decorator. Bind the concrete decorator type once so handlers keep
# their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

VIDEO_MLX_BIN = os.environ.get("VIDEO_MLX_BIN", "ltx-2-mlx")
# Fallback engine (Blaizzy/mlx-video, Wan2.2-TI2V-5B): a console script shipped
# by the `mlx-video` package. Silent MP4 (no audio stream, no --fps flag).
VIDEO_MLX_WAN_BIN = os.environ.get("VIDEO_MLX_WAN_BIN", "mlx_video.wan_2.generate")
VIDEO_MLX_DEFAULT_MODEL = os.environ.get("VIDEO_MLX_DEFAULT_MODEL", "ltx-2.5-q4")
# Long, thermally punishing jobs — a 4s clip runs several minutes on this box.
VIDEO_MLX_TIMEOUT = int(os.environ.get("VIDEO_MLX_TIMEOUT", "1800"))
VIDEO_MLX_LOW_RAM = os.environ.get("VIDEO_MLX_LOW_RAM", "1") not in ("", "0", "false", "no")
VIDEO_MLX_QUALITY = os.environ.get("VIDEO_MLX_QUALITY", "fast")
_JOBS = MediaJobManager()

# Roster key -> engine + the model argument its engine CLI takes. Upstream
# `--help` is the authority; env overrides let an operator repoint a key
# without a code change. `ltx` = dgrauet/ltx-2-mlx (a HF repo id or local pack
# dir; renders synchronized audio). `wan` = mlx-video (needs a locally
# converted MLX dir via VIDEO_MLX_WAN_MODEL_DIR; silent 720p photoreal).
VIDEO_MLX_MODELS: dict[str, dict[str, str]] = {
    "ltx-2.5-q4": {
        "engine": "ltx",
        "model": os.environ.get("VIDEO_MLX_Q4_TAG", "dgrauet/ltx-2.5-mlx-q4"),
    },
    "wan2.2-5b": {
        "engine": "wan",
        "model": os.environ.get("VIDEO_MLX_WAN_MODEL_DIR", "Anes1032/Wan2.2-TI2V-5B-mlx-q8"),
    },
}


def _engine_cfg(model: str) -> dict[str, str]:
    """Roster entry for a model key; unknown keys pass through as LTX model tags."""
    return VIDEO_MLX_MODELS.get(model) or {"engine": "ltx", "model": model}


def _media_model_key(model: str, width: int, height: int) -> str:
    """Size-aware admission key: the LTX peak scales with resolution (measured
    15.8GiB at 512x320, estimated ~25GB at 704x480), Wan2.2-5B does not."""
    if _engine_cfg(model)["engine"] != "ltx":
        return f"video_mlx:{model}"
    bucket = "512" if width * height <= 512 * 320 else "704"
    return f"video_mlx:{model}-{bucket}"


def _round_frames(frames: int, step: int) -> int:
    """VAE temporal compression: LTX needs an 8k+1, Wan a 4n+1 frame count."""
    frames = max(9, int(frames))
    return ((frames - 1) // step) * step + 1


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {"status": "ok", "service": "video-mlx-generation", "models": sorted(VIDEO_MLX_MODELS)}
    )


async def _fetch_source_image(image_url: str) -> Path:
    """Fetch a reference image (public http(s) URL, or an already-uploaded
    workspace file resolved by name/UUID prefix — Rule 11) to a local path."""
    dst = get_generated_dir("videos") / f"src_{uuid.uuid4().hex[:8]}.png"
    if image_url.startswith(("http://", "https://")):
        import httpx

        assert_public_http_url(image_url)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            dst.write_bytes(resp.content)
        return dst
    resolved = resolve_upload_path(image_url)
    if resolved is None:
        raise ValueError(
            f"image_url must be an http(s) URL or an existing upload filename, not: {image_url!r}"
        )
    dst.write_bytes(resolved.read_bytes())
    return dst


def _ltx_cmd(
    cfg: dict[str, str],
    prompt: str,
    frames: int,
    width: int,
    height: int,
    seed: int,
    fps: int,
    out: Path,
    image_path: Path | None,
    quality: str,
) -> list[str]:
    """ltx-2-mlx generate invocation. `quality` picks the sampler: distilled
    (fast) or the two-stage pass (hq). TeaCache is intentionally not exposed —
    upstream raises on LTX-2.5 packs (`--enable-teacache` is 2.3-only)."""
    cmd = [
        VIDEO_MLX_BIN,
        "generate",
        "--prompt",
        prompt,
        "--model",
        cfg["model"],
        "--two-stage" if quality == "hq" else "--distilled",
        "--frames",
        str(frames),
        "--frame-rate",
        str(fps),
        "--width",
        str(width),
        "--height",
        str(height),
        "--seed",
        str(seed),
        "--output",
        str(out),
    ]
    if VIDEO_MLX_LOW_RAM:
        cmd.append("--low-ram")
    if image_path is not None:
        # `--image PATH [FRAME] [STRENGTH]` — anchor the source at frame 0.
        cmd += ["--image", str(image_path), "0", "1.0"]
    return cmd


def _wan_cmd(
    cfg: dict[str, str],
    prompt: str,
    frames: int,
    width: int,
    height: int,
    seed: int,
    out: Path,
    image_path: Path | None,
) -> list[str]:
    """mlx-video Wan2.2 invocation. No fps flag exists; the pipeline writes its
    own frame rate. Steps/guidance default from the model's config."""
    cmd = [
        VIDEO_MLX_WAN_BIN,
        "--model-dir",
        cfg["model"],
        "--prompt",
        prompt,
        "--width",
        str(width),
        "--height",
        str(height),
        "--num-frames",
        str(frames),
        "--seed",
        str(seed),
        "--output-path",
        str(out),
    ]
    if image_path is not None:
        cmd += ["--image", str(image_path)]
    return cmd


async def _generate(
    prompt: str,
    model: str,
    frames: int,
    width: int,
    height: int,
    seed: int,
    fps: int,
    image_path: Path | None = None,
    quality: str = "fast",
) -> dict[str, Any]:
    cfg = _engine_cfg(model)
    engine = cfg["engine"]
    out = get_generated_dir("videos") / f"{engine}_{uuid.uuid4().hex[:8]}.mp4"
    frames = _round_frames(frames, 4 if engine == "wan" else 8)
    if engine == "wan":
        cmd = _wan_cmd(cfg, prompt, frames, width, height, seed, out, image_path)
    else:
        cmd = _ltx_cmd(cfg, prompt, frames, width, height, seed, fps, out, image_path, quality)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=VIDEO_MLX_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "success": False,
            "error": f"{engine} video generation timed out after {VIDEO_MLX_TIMEOUT}s",
        }
    if proc.returncode != 0 or not out.exists():
        return {
            "success": False,
            "error": (err or b"").decode("utf-8", "replace")[-800:]
            or "the video renderer produced no output",
        }
    pub = await publish_file(out)
    url = pub.get("url") or pub.get("error", "publish failed")
    return {
        "success": True,
        "artifact_path": str(out),
        "url": url,
        "download_url": url,
        "model": model,
        "engine": engine,
        "seed": seed,
        "frames": frames,
    }


@mcp.tool()
async def video_start(
    prompt: str,
    model: str = VIDEO_MLX_DEFAULT_MODEL,
    frames: int = 97,
    width: int = 704,
    height: int = 480,
    seed: int = 42,
    fps: int = 24,
    image_url: str | None = None,
    quality: str = VIDEO_MLX_QUALITY,
) -> dict[str, Any]:
    """Start an async video job (text-to-video, or image-to-video via image_url);
    poll video_status(job_id) until 'done' or 'error'.

    quality: 'fast' = distilled sampler, 'hq' = two-stage pass (LTX models only).
    """
    if not prompt:
        return {"success": False, "error": "prompt is required"}
    if quality not in ("fast", "hq"):
        return {"success": False, "error": f"quality must be 'fast' or 'hq', not {quality!r}"}
    model_key = _media_model_key(model, width, height)
    if not _JOBS.is_busy:
        refusal = await admit(model_key)
        if refusal:
            return refusal
    src: Path | None = None
    if image_url:
        try:
            src = await _fetch_source_image(image_url)
        except (ValueError, OSError) as e:
            return {"success": False, "error": str(e)}

    async def _run(progress: Any) -> dict[str, Any]:
        progress(1, "Checking memory before model load…")
        late_refusal = await admit(model_key)
        if late_refusal:
            return late_refusal
        engine = _engine_cfg(model)["engine"]
        rounded = _round_frames(int(frames), 4 if engine == "wan" else 8)
        progress(2, f"Rendering video ({model}, {rounded} frames, quality={quality})…")
        return await _generate(
            prompt,
            model,
            int(frames),
            int(width),
            int(height),
            int(seed),
            int(fps),
            image_path=src,
            quality=quality,
        )

    job_id = _JOBS.start(_run, extra_fields={"model": model, "seed": int(seed), "quality": quality})
    return start_reply(
        job_id,
        "video_status",
        f"model={model}, quality={quality}",
        model=model,
        seed=int(seed),
        quality=quality,
    )


@mcp.tool(meta={"portal5/timeout_s": STATUS_TOOL_TIMEOUT_S})
async def video_status(job_id: str, wait_s: float = DEFAULT_STATUS_WAIT_S) -> dict[str, Any]:
    """Long-poll a video generation job up to wait_s seconds for progress or completion."""
    return await _JOBS.status(job_id, wait_s=wait_s)


@mcp.tool()
async def video_models() -> dict[str, Any]:
    """List the configured video models: engine, model argument, audio support, availability."""
    roster: dict[str, dict[str, Any]] = {}
    for key, cfg in VIDEO_MLX_MODELS.items():
        entry: dict[str, Any] = {
            "engine": cfg["engine"],
            "model": cfg["model"],
            "audio": cfg["engine"] == "ltx",  # LTX renders synchronized audio; Wan is silent
            "default": key == VIDEO_MLX_DEFAULT_MODEL,
        }
        if cfg["engine"] == "wan":
            # mlx-video's --model-dir takes a locally converted MLX dir.
            entry["installed"] = Path(cfg["model"]).expanduser().is_dir()
        roster[key] = entry
    return {"success": True, "models": roster}


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


bind_native_context(mcp)

if __name__ == "__main__":
    main()
