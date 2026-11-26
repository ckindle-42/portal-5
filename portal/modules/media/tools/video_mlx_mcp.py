"""Video-MLX MCP — MLX-native local video generation (Apple Silicon).

Headless wrapper over the ``ltx-2-mlx`` CLI (pure-MLX LTX-2 port) running the
LTX-2.5 packs, with an opt-in ``mlx-video`` Wan2.2-TI2V-5B fallback. Runs on
the host MLX layer (like mflux / mlx-transcribe), NOT in any Docker image.

The tool surface is the shared media async pattern: ``video_start`` submits a
job and returns its id immediately, ``video_status`` polls progress or completion,
and ``video_models`` lists the roster. Memory: the Tier-1 admission check
(``admit``) reclaims idle LLM residents through the Pipeline before a load,
and the per-job subprocess exiting releases Metal memory after one — the
renderer is never kept resident between jobs.

Port 8935 (``VIDEO_MLX_MCP_PORT``). Apple Silicon only; there is no CPU/CUDA
fallback for this engine. Output is preview-grade and practically capped at
~4-6s clips on this hardware.
"""

from __future__ import annotations

import asyncio
import logging
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
    DEFAULT_STATS_DIR,
    DEFAULT_STATUS_WAIT_S,
    STATUS_TOOL_TIMEOUT_S,
    JobDurationStats,
    MediaJobManager,
    start_reply,
)
from portal.platform.mcp_host import assert_public_http_url, resolve_upload_path
from portal.platform.mcp_host.eval_scope import bind_native_context
from portal.platform.mcp_host.owui_files import publish_file
from portal.platform.mcp_host.workspace import get_generated_dir

logger = logging.getLogger(__name__)

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
_STATS = JobDurationStats(DEFAULT_STATS_DIR / "job_durations_video.json")
_JOBS = MediaJobManager(stats=_STATS)
# Bootstrap ETA until measured durations exist for a key.
_ETA_DEFAULT_S = float(os.environ.get("VIDEO_ETA_DEFAULT_S", "900"))

# What a model emits when it means "whatever the roster default is". Sent on as a
# `--model` value it is a HF repo id, and the lookup 404s (2026-11-19:
# `/api/models/default/revision/main`).
_MODEL_PLACEHOLDERS = frozenset({"", "default", "auto", "none", "null"})

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


def _model_key(model: str) -> str:
    """Roster key for a requested model; a placeholder or blank means the roster default."""
    key = (model or "").strip()
    return VIDEO_MLX_DEFAULT_MODEL if key.casefold() in _MODEL_PLACEHOLDERS else key


def _engine_cfg(model: str) -> dict[str, str]:
    """Roster entry for a model key; unknown keys pass through as LTX model tags."""
    key = _model_key(model)
    return VIDEO_MLX_MODELS.get(key) or {"engine": "ltx", "model": key}


def _hf_cache_dir() -> Path:
    """huggingface_hub's hub cache: HF_HUB_CACHE, else HF_HOME/hub, else its default."""
    explicit = os.environ.get("HF_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    home = os.environ.get("HF_HOME")
    if home:
        return Path(home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _cached_pack(repo_id: str) -> Path | None:
    """The pack's downloaded snapshot dir, so a warm cache needs no HF lookup.

    Passing the repo id makes ``_resolve_model_dir`` call ``snapshot_download``,
    which resolves the revision over the network even when the weights are on
    disk; the LTX-2.5 packs carry their own text tower, so a local path renders
    fully offline.
    """
    if "/" not in repo_id:
        return None
    root = _hf_cache_dir() / f"models--{repo_id.replace('/', '--')}"
    snapshots = root / "snapshots"
    if not snapshots.is_dir():
        return None
    ref = root / "refs" / "main"
    revision = ref.read_text().strip() if ref.is_file() else ""
    if not revision or not (snapshots / revision).is_dir():
        dirs = [p for p in snapshots.iterdir() if p.is_dir()]
        if not dirs:
            return None
        revision = max(dirs, key=lambda p: p.stat().st_mtime).name
    pack = snapshots / revision
    return pack if any(pack.glob("*.safetensors")) else None


# Measured LTX frame. 704x480 is an unmeasured ~25GB estimate and is often refused.
_MEASURED_LTX_WIDTH = 512
_MEASURED_LTX_HEIGHT = 320


def _media_model_key(model: str, width: int, height: int) -> str:
    """Size-aware admission key: the LTX peak scales with resolution (measured
    15.8GiB at 512x320, estimated ~25GB at 704x480), Wan2.2-5B does not."""
    key = _model_key(model)
    if _engine_cfg(key)["engine"] != "ltx":
        return f"video_mlx:{key}"
    bucket = "512" if width * height <= 512 * 320 else "704"
    return f"video_mlx:{key}-{bucket}"


def _terminal_memory_refusal(refusal: dict[str, Any]) -> dict[str, Any]:
    """A same-turn retry cannot free the model serving the turn, so the refusal is final."""
    error = str(refusal.get("error") or "Not enough free memory to start a video.")
    text = (
        f"{error} No video was started; this check finished immediately. "
        f"A started render is limited to {VIDEO_MLX_TIMEOUT}s and video_status waits up to "
        f"{int(DEFAULT_STATUS_WAIT_S)}s. Do not call video_start again in this turn; "
        "repeat this error to the user."
    )
    logger.warning("video_start memory refusal: %s", error)
    return {**refusal, "success": False, "retryable": False, "error": text, "user_error": text}


async def _admit_size(
    model: str, width: int, height: int
) -> tuple[str, int, int, dict[str, Any] | None]:
    """Admit the requested frame, or the measured 512x320 LTX frame when the larger one does not fit."""
    width, height = int(width), int(height)
    key = _media_model_key(model, width, height)
    refusal = await admit(key)
    if not refusal:
        return key, width, height, None
    if (
        _engine_cfg(model)["engine"] == "ltx"
        and width * height > _MEASURED_LTX_WIDTH * _MEASURED_LTX_HEIGHT
    ):
        safe_key = _media_model_key(model, _MEASURED_LTX_WIDTH, _MEASURED_LTX_HEIGHT)
        safe_refusal = await admit(safe_key)
        if not safe_refusal:
            logger.info(
                "video_start shrinking %sx%s to %sx%s after admission refusal",
                width,
                height,
                _MEASURED_LTX_WIDTH,
                _MEASURED_LTX_HEIGHT,
            )
            return safe_key, _MEASURED_LTX_WIDTH, _MEASURED_LTX_HEIGHT, None
        refusal = safe_refusal
    return key, width, height, _terminal_memory_refusal(refusal)


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
    if engine == "ltx":
        local_pack = _cached_pack(cfg["model"])
        if local_pack is not None:
            cfg = {**cfg, "model": str(local_pack)}
    out = get_generated_dir("videos") / f"{engine}_{uuid.uuid4().hex[:8]}.mp4"
    frames = _round_frames(frames, 4 if engine == "wan" else 8)
    if engine == "wan":
        cmd = _wan_cmd(cfg, prompt, frames, width, height, seed, out, image_path)
    else:
        cmd = _ltx_cmd(cfg, prompt, frames, width, height, seed, fps, out, image_path, quality)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    started = asyncio.get_running_loop().time()
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=VIDEO_MLX_TIMEOUT)
    except TimeoutError:
        logger.error(
            "%s video renderer hit external safety ceiling after %.1fs (limit %ds); terminating child",
            engine,
            asyncio.get_running_loop().time() - started,
            VIDEO_MLX_TIMEOUT,
        )
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
        "duration_seconds": frames / fps,
    }


def _note_shrunk(
    result: dict[str, Any], requested: tuple[int, int], size: tuple[int, int]
) -> dict[str, Any]:
    """Record when admission rendered a smaller frame than the one requested."""
    if result.get("success") and size != requested:
        result["resolution_note"] = (
            f"Rendered at {size[0]}x{size[1]} because {requested[0]}x{requested[1]} "
            "did not fit in free memory."
        )
        result["width"] = size[0]
        result["height"] = size[1]
    return result


async def _render_admitted(
    progress: Any,
    *,
    prompt: str,
    resolved: str,
    frames: int,
    requested: tuple[int, int],
    render_w: int,
    render_h: int,
    seed: int,
    fps: int,
    quality: str,
    src: Path | None,
) -> dict[str, Any]:
    """Re-check memory, render, and note a shrink from the requested frame."""
    progress(1, "Checking memory before model load…")
    _late_key, late_w, late_h, late = await _admit_size(resolved, render_w, render_h)
    if late:
        return late
    engine = _engine_cfg(resolved)["engine"]
    rounded = _round_frames(int(frames), 4 if engine == "wan" else 8)
    progress(
        2, f"Rendering video ({resolved}, {rounded} frames, {late_w}x{late_h}, quality={quality})…"
    )
    result = await _generate(
        prompt,
        resolved,
        int(frames),
        late_w,
        late_h,
        int(seed),
        int(fps),
        image_path=src,
        quality=quality,
    )
    return _note_shrunk(result, requested, (late_w, late_h))


@mcp.tool()
async def video_start(
    prompt: str,
    model: str = VIDEO_MLX_DEFAULT_MODEL,
    frames: int = 97,
    width: int = _MEASURED_LTX_WIDTH,
    height: int = _MEASURED_LTX_HEIGHT,
    seed: int = 42,
    fps: int = 24,
    image_url: str | None = None,
    quality: str = VIDEO_MLX_QUALITY,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Start a video job. duration_seconds overrides frames; a frame that does not fit renders at 512x320."""
    if not prompt:
        return {"success": False, "error": "prompt is required"}
    if quality not in ("fast", "hq"):
        return {"success": False, "error": f"quality must be 'fast' or 'hq', not {quality!r}"}
    if duration_seconds is not None:
        frames = min(145, max(25, int(round(duration_seconds * fps)) + 1))
    resolved = _model_key(model)
    requested = (int(width), int(height))
    render_w, render_h = requested
    if not _JOBS.is_busy:
        _key, render_w, render_h, refusal = await _admit_size(resolved, *requested)
        if refusal:
            return refusal
    src: Path | None = None
    if image_url:
        try:
            src = await _fetch_source_image(image_url)
        except (ValueError, OSError) as e:
            return {"success": False, "error": str(e)}

    async def _run(progress: Any) -> dict[str, Any]:
        return await _render_admitted(
            progress,
            prompt=prompt,
            resolved=resolved,
            frames=int(frames),
            requested=requested,
            render_w=render_w,
            render_h=render_h,
            seed=int(seed),
            fps=int(fps),
            quality=quality,
            src=src,
        )

    engine = _engine_cfg(resolved)["engine"]
    eta_key = f"video:{engine}:{_round_frames(int(frames), 4 if engine == 'wan' else 8)}f:{quality}"
    eta_s = _STATS.eta_s(eta_key, _ETA_DEFAULT_S)
    job_id = _JOBS.start(
        _run,
        extra_fields={"model": resolved, "seed": int(seed), "quality": quality},
        eta_key=eta_key,
        eta_s=eta_s,
    )
    logger.info(
        "video job %s queued model=%s %sx%s quality=%s budget=%ss",
        job_id,
        resolved,
        render_w,
        render_h,
        quality,
        VIDEO_MLX_TIMEOUT,
    )
    return start_reply(
        job_id,
        "video_status",
        (
            f"model={resolved}, quality={quality}, {render_w}x{render_h}, "
            f"render budget {VIDEO_MLX_TIMEOUT}s"
        ),
        model=resolved,
        seed=int(seed),
        quality=quality,
        width=render_w,
        height=render_h,
        eta_s=eta_s,
    )


@mcp.tool(meta={"portal5/timeout_s": STATUS_TOOL_TIMEOUT_S})
async def video_status(job_id: str, wait_s: float = DEFAULT_STATUS_WAIT_S) -> dict[str, Any]:
    """Poll a video job for progress or completion; done carries download_url."""
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
