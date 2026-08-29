"""Video-MLX MCP — MLX-native local video generation (Apple Silicon).

Headless wrapper over the ``ltx-2-mlx`` CLI (pure-MLX LTX-2 port). Runs on the
host MLX layer (like mflux / mlx-transcribe), NOT in any Docker image. Replaces
the removed ComfyUI ``video_mcp`` path — the tools are deliberately named
``generate_video`` / ``animate_image`` so repointing the video workspace is a
backend swap, not a tool-rename cascade.

Port 8935 (``VIDEO_MLX_MCP_PORT``). Apple Silicon only; there is no CPU/CUDA
fallback for this engine. Output is preview-grade and practically capped at
~4-6s clips on this hardware.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from mcp.server import MCPServer
from starlette.responses import JSONResponse

from portal.modules.media.tools._admission import admit
from portal.platform.data_loader import load_data
from portal.platform.mcp_host import assert_public_http_url, resolve_upload_path
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import get_generated_dir

port = int(os.getenv("VIDEO_MLX_MCP_PORT", "8935"))
mcp = MCPServer("video-mlx-generation")

VIDEO_MLX_BIN = os.environ.get("VIDEO_MLX_BIN", "ltx-2-mlx")
VIDEO_MLX_DEFAULT_MODEL = os.environ.get("VIDEO_MLX_DEFAULT_MODEL", "ltx-2.3-q4")
# Long, thermally punishing jobs — a 4s clip runs several minutes on this box.
VIDEO_MLX_TIMEOUT = int(os.environ.get("VIDEO_MLX_TIMEOUT", "1800"))
VIDEO_MLX_LOW_RAM = os.environ.get("VIDEO_MLX_LOW_RAM", "1") not in ("", "0", "false", "no")
VIDEO_MLX_MODE = os.environ.get("VIDEO_MLX_MODE", "--distilled")  # fastest; --two-stage for quality

# Roster key -> ltx-2-mlx --model pack. `ltx-2-mlx generate --help` is the
# authority; env overrides let an operator repoint without a code change.
VIDEO_MLX_MODELS: dict[str, str] = {
    "ltx-2.3-q4": os.environ.get("VIDEO_MLX_Q4_TAG", "dgrauet/ltx-2.3-mlx-q4"),
    "ltx-2.3-q8": os.environ.get("VIDEO_MLX_Q8_TAG", "dgrauet/ltx-2.3-mlx-q8"),
}


def _media_model_key(model: str | None) -> str:
    return f"video_mlx:{model or VIDEO_MLX_DEFAULT_MODEL}"


def _round_frames(frames: int) -> int:
    """LTX VAE temporal compression requires an 8k+1 frame count."""
    frames = max(9, int(frames))
    return ((frames - 1) // 8) * 8 + 1


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse(
        {"status": "ok", "service": "video-mlx-generation", "models": sorted(VIDEO_MLX_MODELS)}
    )


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_video_mlx_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


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


async def _generate(
    prompt: str,
    model: str,
    frames: int,
    width: int,
    height: int,
    seed: int,
    fps: int,
    image_path: Path | None = None,
) -> dict:
    out = get_generated_dir("videos") / f"ltx_{uuid.uuid4().hex[:8]}.mp4"
    cmd = [
        VIDEO_MLX_BIN,
        "generate",
        "--prompt",
        prompt,
        "--model",
        VIDEO_MLX_MODELS.get(model, model),
        VIDEO_MLX_MODE,
        "--frames",
        str(_round_frames(frames)),
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
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=VIDEO_MLX_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"success": False, "error": f"ltx-2-mlx timed out after {VIDEO_MLX_TIMEOUT}s"}
    if proc.returncode != 0 or not out.exists():
        return {
            "success": False,
            "error": (err or b"").decode("utf-8", "replace")[-800:]
            or "ltx-2-mlx produced no output",
        }
    pub = await publish_file(out)
    return {
        "success": True,
        "url": pub.get("url") or pub.get("error", "publish failed"),
        "model": model,
        "seed": seed,
        "frames": _round_frames(frames),
    }


@mcp.tool()
async def generate_video(
    prompt: str,
    model: str = VIDEO_MLX_DEFAULT_MODEL,
    frames: int = 97,
    width: int = 704,
    height: int = 480,
    seed: int = 42,
    fps: int = 24,
) -> dict:
    """Generate a short video clip (with audio) from a text prompt using LTX-2.3."""
    if not prompt:
        return {"success": False, "error": "prompt is required"}
    refusal = await admit(_media_model_key(model))
    if refusal:
        return refusal
    return await _generate(prompt, model, int(frames), int(width), int(height), int(seed), int(fps))


@mcp.tool()
async def animate_image(
    image_url: str,
    prompt: str,
    model: str = VIDEO_MLX_DEFAULT_MODEL,
    frames: int = 97,
    width: int = 704,
    height: int = 480,
    seed: int = 42,
    fps: int = 24,
) -> dict:
    """Animate a still image into a short clip (image-to-video) using LTX-2.3.

    `image_url` is a public http(s) URL or an already-uploaded workspace file name.
    """
    if not image_url or not prompt:
        return {"success": False, "error": "image_url and prompt are required"}
    refusal = await admit(_media_model_key(model))
    if refusal:
        return refusal
    try:
        src = await _fetch_source_image(image_url)
    except (ValueError, OSError) as e:
        return {"success": False, "error": str(e)}
    return await _generate(
        prompt, model, int(frames), int(width), int(height), int(seed), int(fps), image_path=src
    )


@mcp.custom_route("/tools/generate_video", methods=["POST"])
async def generate_video_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(await generate_video(**a))


@mcp.custom_route("/tools/animate_image", methods=["POST"])
async def animate_image_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(await animate_image(**a))


def main():
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
