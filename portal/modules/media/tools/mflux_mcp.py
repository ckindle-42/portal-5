"""MFLUX MCP — MLX-native local image generation (Apple Silicon).

Headless wrapper over the ``mflux-generate`` CLI. Runs on the host MLX layer
(like mlx-transcribe / reranker / embedding), NOT in any Docker image. Replaces
the removed ComfyUI image path — the tools are deliberately named
``generate_image`` / ``edit_image`` so repointing the image workspaces is a
backend swap, not a tool-rename cascade.

Port 8933 (``MFLUX_MCP_PORT``). Apple Silicon only; there is no CPU/CUDA
fallback for this engine.
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

port = int(os.getenv("MFLUX_MCP_PORT", "8933"))
mcp = MCPServer("mflux-generation")

# mflux ships two CLIs: `mflux-generate` for FLUX.1 / schnell / dev / z-image /
# qwen-image, and `mflux-generate-flux2` for the FLUX.2 Klein family. MFLUX_BIN
# is the base; the flux2 entry point is derived from it (or overridden).
MFLUX_BIN = os.environ.get("MFLUX_BIN", "mflux-generate")
MFLUX_FLUX2_BIN = os.environ.get("MFLUX_FLUX2_BIN") or (
    f"{MFLUX_BIN}-flux2" if not MFLUX_BIN.endswith("-flux2") else MFLUX_BIN
)
MFLUX_FLUX2_MODELS = frozenset({"klein"})
MFLUX_DEFAULT_MODEL = os.environ.get("MFLUX_DEFAULT_MODEL", "schnell")
MFLUX_TIMEOUT = int(os.environ.get("MFLUX_TIMEOUT", "900"))
MFLUX_QUANTIZE = os.environ.get("MFLUX_QUANTIZE", "8")
MFLUX_LOW_RAM = os.environ.get("MFLUX_LOW_RAM", "1") not in ("", "0", "false", "no")

# Roster key -> the value the installed mflux-generate accepts for --model.
# `mflux-generate --help` is the authority on the exact built-in tags; the env
# overrides let an operator repoint a key without a code change.
MFLUX_MODELS: dict[str, str] = {
    "schnell": os.environ.get("MFLUX_SCHNELL_TAG", "schnell"),
    "dev": os.environ.get("MFLUX_DEV_TAG", "dev"),
    "klein": os.environ.get("MFLUX_KLEIN_TAG", "flux2-klein-4b"),
    "z-image": os.environ.get("MFLUX_ZIMAGE_TAG", "z-image-turbo"),
    "qwen-image": os.environ.get("MFLUX_QWEN_TAG", "qwen-image"),
    "qwen-image-edit": os.environ.get("MFLUX_QWEN_EDIT_TAG", "qwen-image-edit"),
}

# Per-model default step counts — the turbo/schnell distills need only a handful,
# the full models want ~20+. Callers can always override via the `steps` arg.
MFLUX_DEFAULT_STEPS: dict[str, int] = {
    "schnell": 4,
    "dev": 20,
    "klein": 28,
    "z-image": 8,
    "qwen-image": 20,
    "qwen-image-edit": 20,
}


def _media_model_key(model: str | None) -> str:
    """Map a model override to the `mflux:*` admission key. Unknown models fall
    through to admit()'s conservative default rather than being guessed at."""
    return f"mflux:{model or MFLUX_DEFAULT_MODEL}"


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse(
        {"status": "ok", "service": "mflux-generation", "models": sorted(MFLUX_MODELS)}
    )


TOOLS_MANIFEST = load_data("config/inference", "tools_manifest_mflux_mcp")


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


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


async def _generate(
    prompt: str,
    model: str,
    steps: int,
    seed: int,
    width: int,
    height: int,
    image_path: Path | None = None,
    strength: float | None = None,
) -> dict:
    out = get_generated_dir("images") / f"mflux_{uuid.uuid4().hex[:8]}.png"
    cli_model = MFLUX_MODELS.get(model, model)
    bin_ = MFLUX_FLUX2_BIN if model in MFLUX_FLUX2_MODELS else MFLUX_BIN
    cmd = [
        bin_,
        "--model",
        cli_model,
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
    if image_path is not None:
        # `--image PATH [STRENGTH]` — strength is a positional following the path.
        cmd += ["--image", str(image_path)]
        if strength is not None:
            cmd.append(str(strength))
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
    return {
        "success": True,
        "url": pub.get("url") or pub.get("error", "publish failed"),
        "model": model,
        "seed": seed,
    }


@mcp.tool()
async def generate_image(
    prompt: str,
    model: str = MFLUX_DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    steps: int | None = None,
    seed: int = 1,
) -> dict:
    """Generate an image from a text prompt using MLX-native FLUX (MFLUX)."""
    if not prompt:
        return {"success": False, "error": "prompt is required"}
    refusal = await admit(_media_model_key(model))
    if refusal:
        return refusal
    return await _generate(
        prompt,
        model,
        int(steps or MFLUX_DEFAULT_STEPS.get(model, 4)),
        int(seed),
        int(width),
        int(height),
    )


@mcp.tool()
async def edit_image(
    image_url: str,
    prompt: str,
    model: str = "qwen-image-edit",
    strength: float = 0.6,
    width: int = 1024,
    height: int = 1024,
    steps: int | None = None,
    seed: int = 1,
) -> dict:
    """Edit an existing image by instruction (qwen-image-edit) or img2img.

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
        prompt,
        model,
        int(steps or MFLUX_DEFAULT_STEPS.get(model, 20)),
        int(seed),
        int(width),
        int(height),
        image_path=src,
        strength=float(strength),
    )


@mcp.custom_route("/tools/generate_image", methods=["POST"])
async def generate_image_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(await generate_image(**a))


@mcp.custom_route("/tools/edit_image", methods=["POST"])
async def edit_image_endpoint(request):
    a = (await request.json()).get("arguments", {})
    return JSONResponse(await edit_image(**a))


def main():
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
