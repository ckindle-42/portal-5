"""MFLUX MCP — MLX-native local image generation (Apple Silicon).

Headless wrapper over the per-family ``mflux-generate-*`` CLIs (mflux >=0.24.0).
Runs on the host MLX layer (like mlx-transcribe / reranker / embedding), NOT in
any Docker image. Replaces the removed ComfyUI image path — the tools are
deliberately named ``generate_image`` / ``edit_image`` so repointing the image
workspaces is a backend swap, not a tool-rename cascade.

Roster (MEDIA_OVERHAUL_RESEARCH §1.3): ``flux2-klein`` (FLUX.2 klein 4B, 4-step
distilled, Apache 2.0 — default fast T2I), ``flux3-klein`` (FLUX 3 Image Klein,
16-step distilled, multi-ref editing), ``qwen-2.1`` (2.1-turbo 8 steps,
typography/instruction editing), ``z-image`` (Z-Image-Turbo, Apache 2.0
fallback). The retired FLUX.1/20B tags (schnell, dev, qwen-image) are not in
the roster but still pass through untouched (base binary + raw tag) for an
operator who re-pulls them.

Memory: subprocess-per-job — each ``mflux-generate-*`` process exits when its
image is written, so nothing model-sized stays resident between jobs and the
idle-release callback has nothing to release. ``admit()`` (with Pipeline
``/admin/reclaim-idle`` eviction) runs before every load.

Port 8933 (``MFLUX_MCP_PORT``). Apple Silicon only; there is no CPU/CUDA
fallback for this engine.
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

port = int(os.getenv("MFLUX_MCP_PORT", "8933"))
mcp = MCPServer("mflux-generation")

# MCPServer.custom_route() has no return annotation upstream (mcp SDK), so mypy
# sees its decorator result as Any and flags every routed handler with
# untyped-decorator. Bind the concrete decorator type once so handlers keep
# their annotations.
_route: Callable[
    ...,
    Callable[[Callable[..., Awaitable[Response]]], Callable[..., Awaitable[Response]]],
] = mcp.custom_route

# mflux 0.24+ ships a separate entry-point binary per model family — routing a
# non-FLUX.1 model through the base `mflux-generate` silently falls back to the
# FLUX weight loader (it then dies looking for a `text_encoder_2/`). MFLUX_BIN is
# the base (FLUX.1 schnell/dev); the family binaries are derived from its dirname
# so an operator only sets MFLUX_BIN once (e.g. to a venv path).
MFLUX_BIN = os.environ.get("MFLUX_BIN", "mflux-generate")
_BIN_DIR = os.path.dirname(MFLUX_BIN)
_BIN_STEM = os.path.basename(MFLUX_BIN).removesuffix("-flux2")  # tolerate a *-flux2 override


def _family_bin(suffix: str) -> str:
    name = f"{_BIN_STEM}-{suffix}" if suffix else _BIN_STEM
    return os.path.join(_BIN_DIR, name) if _BIN_DIR else name


# roster key -> mflux entry-point binary. Env overrides win.
MFLUX_MODEL_BIN: dict[str, str] = {
    "flux2-klein": os.environ.get("MFLUX_FLUX2_BIN") or _family_bin("flux2"),
    "flux3-klein": os.environ.get("MFLUX_FLUX3_BIN") or _family_bin("flux3"),
    "qwen-2.1": os.environ.get("MFLUX_QWEN21_BIN") or _family_bin("qwen-2.1"),
    "z-image": os.environ.get("MFLUX_ZIMAGE_BIN") or _family_bin("z-image-turbo"),
}

MFLUX_DEFAULT_MODEL = os.environ.get("MFLUX_DEFAULT_MODEL", "flux2-klein")
MFLUX_TIMEOUT = int(os.environ.get("MFLUX_TIMEOUT", "900"))
MFLUX_QUANTIZE = os.environ.get("MFLUX_QUANTIZE", "8")
MFLUX_LOW_RAM = os.environ.get("MFLUX_LOW_RAM", "1") not in ("", "0", "false", "no")
# mflux 0.24: float16 attention/FFN compute (M1-family speedup; output shifts
# slightly per seed). Empty/none keeps the model's own precision.
MFLUX_COMPUTE_PRECISION = os.environ.get("MFLUX_COMPUTE_PRECISION", "float16").strip().lower()
_JOBS = MediaJobManager()

# Roster key -> the `--model` value its family binary (MFLUX_MODEL_BIN) accepts.
# `<binary> --help` is the authority on the exact built-in tags; the env overrides
# let an operator repoint a key without a code change.
MFLUX_MODELS: dict[str, str] = {
    "flux2-klein": os.environ.get("MFLUX_FLUX2_KLEIN_TAG", "flux2-klein-4b"),
    "flux3-klein": os.environ.get("MFLUX_FLUX3_KLEIN_TAG", "flux3-image-klein"),
    "qwen-2.1": os.environ.get("MFLUX_QWEN21_TAG", "qwen-image-2.1-turbo"),
    "z-image": os.environ.get("MFLUX_ZIMAGE_TAG", "z-image-turbo"),
}

# Roster key -> the *-edit family binary suffix used for instruction editing
# (repeatable --image-paths, mflux 0.24 edit CLIs — no positional strength).
MFLUX_EDIT_SUFFIX: dict[str, str] = {
    "flux2-klein": "flux2-edit",
    "flux3-klein": "flux3-edit",
    "qwen-2.1": "qwen-2.1-edit",
}

# Per-model default step counts — the turbo/schnell distills need only a handful,
# the full models want ~20+. Callers can always override via the `steps` arg.
# The retired FLUX.1 tags fall back to schnell's 4 (dev needs its steps passed).
MFLUX_DEFAULT_STEPS: dict[str, int] = {
    "flux2-klein": 4,
    "flux3-klein": 16,
    "qwen-2.1": 8,
    "z-image": 8,
    "schnell": 4,
}


def _media_model_key(model: str | None) -> str:
    """Map a model override to the `mflux:*` admission key. Unknown models fall
    through to admit()'s conservative default rather than being guessed at."""
    return f"mflux:{model or MFLUX_DEFAULT_MODEL}"


@_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse(
        {"status": "ok", "service": "mflux-generation", "models": sorted(MFLUX_MODELS)}
    )


async def _fetch_source_image(image_url: str) -> Path:
    """Fetch a reference image from a public http(s) URL or an already-uploaded
    workspace file to a local path under the generated-images dir. Local paths
    are never trusted verbatim (Rule 11) — only files already inside the shared
    uploads dir, resolved by exact filename / UUID prefix."""
    dst = get_generated_dir("images") / f"src_{uuid.uuid4().hex[:8]}.png"
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


def _mflux_cmd(
    prompt: str,
    model: str,
    steps: int,
    seed: int,
    width: int,
    height: int,
    out: Path,
    image_paths: list[Path] | None = None,
) -> list[str] | dict[str, Any]:
    """Build one mflux CLI invocation, or an error dict for an unsupported edit.

    Instruction edits run the family's *-edit binary with repeatable
    ``--image-paths`` (mflux 0.24 edit CLIs take no positional strength).
    Text-to-image runs the family's T2I binary. The float16 compute flag is
    family-only — the legacy FLUX.1 base binary does not accept it.
    """
    if image_paths:
        suffix = MFLUX_EDIT_SUFFIX.get(model)
        if suffix is None:
            return {
                "success": False,
                "error": (
                    f"model {model!r} has no edit binary; edit_image supports "
                    f"{sorted(MFLUX_EDIT_SUFFIX)}"
                ),
            }
        bin_ = _family_bin(suffix)
    else:
        bin_ = MFLUX_MODEL_BIN.get(model, MFLUX_BIN)
    cmd = [
        bin_,
        "--model",
        MFLUX_MODELS.get(model, model),
        "--prompt",
        prompt,
        "--steps",
        str(steps),
        "--quantize",
        MFLUX_QUANTIZE,
        "--seed",
        str(seed),
        "--width",
        str(width),
        "--height",
        str(height),
        "--output",
        str(out),
        "--no-metadata",
    ]
    if MFLUX_LOW_RAM:
        cmd.append("--low-ram")
    if bin_ != MFLUX_BIN and MFLUX_COMPUTE_PRECISION not in ("", "none", "off"):
        cmd += ["--compute-precision", MFLUX_COMPUTE_PRECISION]
    for path in image_paths or []:
        cmd += ["--image-paths", str(path)]
    return cmd


async def _generate(
    prompt: str,
    model: str,
    steps: int,
    seed: int,
    width: int,
    height: int,
    image_paths: list[Path] | None = None,
) -> dict[str, Any]:
    out = get_generated_dir("images") / f"mflux_{uuid.uuid4().hex[:8]}.png"
    built = _mflux_cmd(prompt, model, steps, seed, width, height, out, image_paths)
    if isinstance(built, dict):
        return built
    proc = await asyncio.create_subprocess_exec(
        *built, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=MFLUX_TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"success": False, "error": f"mflux timed out after {MFLUX_TIMEOUT}s"}
    if proc.returncode != 0 or not out.exists():
        return {
            "success": False,
            "error": (err or b"").decode("utf-8", "replace")[-800:] or "mflux produced no output",
        }
    pub = await publish_file(out)
    url = pub.get("url") or pub.get("error", "publish failed")
    return {
        "success": True,
        "artifact_path": str(out),
        "url": url,
        "download_url": url,
        "model": model,
        "seed": seed,
    }


@mcp.tool(meta={"portal5/timeout_s": MFLUX_TIMEOUT})
async def generate_image(
    prompt: str,
    model: str = MFLUX_DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    steps: int | None = None,
    seed: int = 1,
) -> dict[str, Any]:
    """Generate an image from a text prompt using MLX-native MFLUX."""
    if not prompt:
        return {"success": False, "error": "prompt is required"}
    refusal = await admit(_media_model_key(model))
    if refusal:
        return refusal
    return await _JOBS.run_serialized(
        lambda: _generate(
            prompt,
            model,
            int(steps or MFLUX_DEFAULT_STEPS.get(model, 4)),
            int(seed),
            int(width),
            int(height),
        )
    )


@mcp.tool(meta={"portal5/timeout_s": MFLUX_TIMEOUT})
async def edit_image(
    image_url: str,
    prompt: str,
    model: str = "qwen-2.1",
    width: int = 1024,
    height: int = 1024,
    steps: int | None = None,
    seed: int = 1,
) -> dict[str, Any]:
    """Edit an existing image by instruction (mflux 0.24 *-edit binaries).

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
    return await _JOBS.run_serialized(
        lambda: _generate(
            prompt,
            model,
            int(steps or MFLUX_DEFAULT_STEPS.get(model, 8)),
            int(seed),
            int(width),
            int(height),
            image_paths=[src],
        )
    )


@mcp.tool()
async def image_start(
    prompt: str,
    model: str = MFLUX_DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    steps: int | None = None,
    seed: int = 1,
    image_url: str | None = None,
) -> dict[str, Any]:
    """Start an async MFLUX image generation or edit job; poll image_status(job_id)."""
    if not prompt:
        return {"success": False, "error": "prompt is required"}
    model_key = _media_model_key(model)
    if not _JOBS.is_busy:
        refusal = await admit(model_key)
        if refusal:
            return refusal
    srcs: list[Path] = []
    if image_url:
        try:
            srcs = [await _fetch_source_image(image_url)]
        except (ValueError, OSError) as e:
            return {"success": False, "error": str(e)}
    resolved_steps = int(steps or MFLUX_DEFAULT_STEPS.get(model, 8 if srcs else 4))

    async def _run(progress: Any) -> dict[str, Any]:
        progress(1, "Checking memory before model load…")
        late_refusal = await admit(model_key)
        if late_refusal:
            return late_refusal
        progress(2, f"Generating image ({model}, {resolved_steps} steps)…")
        return await _generate(
            prompt,
            model,
            resolved_steps,
            int(seed),
            int(width),
            int(height),
            image_paths=srcs or None,
        )

    job_id = _JOBS.start(_run, extra_fields={"model": model, "seed": int(seed)})
    return start_reply(job_id, "image_status", f"model={model}", model=model, seed=int(seed))


@mcp.tool(meta={"portal5/timeout_s": STATUS_TOOL_TIMEOUT_S})
async def image_status(job_id: str, wait_s: float = DEFAULT_STATUS_WAIT_S) -> dict[str, Any]:
    """Long-poll an MFLUX image job up to wait_s seconds for progress or completion."""
    return await _JOBS.status(job_id, wait_s=wait_s)


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


bind_native_context(mcp)

if __name__ == "__main__":
    main()
