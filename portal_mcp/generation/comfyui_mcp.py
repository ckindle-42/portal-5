"""
ComfyUI MCP Server
Wraps the ComfyUI workflow API as MCP tools.
Exposes: generate_image, list_workflows, get_generation_status

Requires: ComfyUI running at COMFYUI_URL (default :8188)
Start with: python -m mcp.generation.comfyui_mcp
"""

import asyncio
import os
import time
import uuid

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("comfyui-generation")

# Configurable timeout: COMFYUI_TIMEOUT env var (seconds, default 1200 = 20 min).
# SDXL at 25 steps can take 5+ min on MPS; FLUX schnell is faster but still variable.
COMFYUI_TIMEOUT = int(os.environ.get("COMFYUI_TIMEOUT", "1200"))

# Module-level httpx client — created once per process, reused for all requests.
# Eliminates TCP/TLS handshake overhead on every image generation call (P9).
_http_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=float(COMFYUI_TIMEOUT), limits=httpx.Limits(max_connections=5)
        )
    return _http_client


async def _close_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "comfyui-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "generate_image",
        "description": "Generate an image using FLUX.1 or SDXL via ComfyUI",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate",
                },
                "model": {
                    "type": "string",
                    "description": "Model to use: 'flux' (fast), 'flux-uncensored' (uncensored), 'sdxl' (high quality). Defaults to IMAGE_BACKEND env var or 'flux'.",
                    "default": "flux",
                },
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels",
                    "default": 1024,
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels",
                    "default": 1024,
                },
                "steps": {
                    "type": "integer",
                    "description": "Number of diffusion steps",
                    "default": 4,
                },
                "cfg": {"type": "number", "description": "CFG scale", "default": 1.0},
                "negative_prompt": {
                    "type": "string",
                    "description": "Negative prompt",
                    "default": "",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed (-1 for random)",
                    "default": -1,
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "list_workflows",
        "description": "List available ComfyUI workflows",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_generation_status",
        "description": "Check the status of a generation task",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task ID to check"},
            },
            "required": ["task_id"],
        },
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})


COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
IMAGE_BACKEND = os.getenv("IMAGE_BACKEND", "flux")  # "flux", "flux-uncensored", or "sdxl"

# FLUX.1 workflow — split-loader approach.
# The official FLUX.1-schnell model from black-forest-labs is UNet-only (no embedded
# CLIP or VAE). CheckpointLoaderSimple returns None for clip/vae on these files.
# We use separate DualCLIPLoader (CLIP-L + T5-XXL) and VAELoader (ae.safetensors).
# Node layout (ComfyUI v0.16+):
#   1: CheckpointLoaderSimple(ckpt_name) → model[0]  (UNet; clip/vae slots are None)
#   2: DualCLIPLoader(clip_name1, clip_name2, type="flux") → clip[0]
#   3: VAELoader(vae_name) → vae[0]
#   4: CLIPTextEncode (positive) → conditioning[0]  ← clip from [2,0]
#   5: CLIPTextEncode (negative) → conditioning[0]  ← clip from [2,0]
#   6: EmptyLatentImage → latent[0]
#   7: FluxGuidance → conditioning[0]  ← conditioning from [4,0]
#   8: KSampler → latent[0]  ← model[1,0], positive[7,0], negative[5,0], latent[6,0]
#   9: VAEDecode → image[0]  ← samples[8,0], vae[3,0]
#  10: SaveImage
# All filenames are set dynamically at runtime from env vars (see generate_image).
FLUX_WORKFLOW = {
    "1": {
        "inputs": {"ckpt_name": "flux1-schnell.safetensors"},
        "class_type": "CheckpointLoaderSimple",
    },
    "2": {
        "inputs": {
            "clip_name1": "text_encoder/model.safetensors",
            "clip_name2": "text_encoder_2/model-00001-of-00002.safetensors",
            "type": "flux",
        },
        "class_type": "DualCLIPLoader",
    },
    "3": {
        "inputs": {"vae_name": "ae.safetensors"},
        "class_type": "VAELoader",
    },
    "4": {
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
    "5": {
        # Empty negative — KSampler requires a conditioning tensor, not empty string.
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
    "6": {
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "7": {
        "inputs": {"conditioning": ["4", 0], "guidance": 3.5},
        "class_type": "FluxGuidance",
    },
    "8": {
        "inputs": {
            "seed": 42,
            "steps": 4,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
            "model": ["1", 0],
            "positive": ["7", 0],
            "negative": ["5", 0],
            "latent_image": ["6", 0],
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
    "9": {
        "inputs": {"samples": ["8", 0], "vae": ["3", 0]},
        "class_type": "VAEDecode",
    },
    "10": {
        "inputs": {"filename_prefix": "portal_", "images": ["9", 0]},
        "class_type": "SaveImage",
    },
}

# SDXL workflow template - uses EmptyLatentImage and has negative prompt
# ComfyUI v0.16: node IDs must be strings (not integers), connections as [node_id, output_index]
SDXL_WORKFLOW = {
    "1": {
        "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        "class_type": "CheckpointLoaderSimple",
    },
    "2": {"inputs": {"text": "", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
    "3": {"inputs": {"text": "", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
    "4": {
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "5": {
        "inputs": {
            "model": ["1", 0],
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "seed": 42,
            "steps": 25,
            "cfg": 7.5,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
    "6": {"inputs": {"samples": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
    "7": {"inputs": {"filename_prefix": "portal_", "images": ["6", 0]}, "class_type": "SaveImage"},
}


# Model → checkpoint file mapping (can override with FLUX_CKPT_FILE env var)
_MODEL_CKPT_MAP = {
    "flux": "flux1-schnell.safetensors",
    "flux-uncensored": "Flux_v8-NSFW.safetensors",
}


def _get_workflow(model: str | None = None) -> dict:
    """Get a deep copy of the workflow for the selected model.

    Args:
        model: Model name ('flux', 'flux-uncensored', 'sdxl') or None to use IMAGE_BACKEND env var.
    """
    import copy

    selected = model or IMAGE_BACKEND
    if selected == "sdxl":
        return copy.deepcopy(SDXL_WORKFLOW)
    return copy.deepcopy(FLUX_WORKFLOW)


def _get_checkpoint(model: str | None = None) -> str:
    """Get the checkpoint filename for the selected model.

    Args:
        model: Model name or None to use IMAGE_BACKEND env var.
    Returns:
        Checkpoint filename from FLUX_CKPT_FILE env var (if set) or auto-selected based on model.
    """
    # If FLUX_CKPT_FILE is explicitly set, respect it
    if os.getenv("FLUX_CKPT_FILE"):
        return os.getenv("FLUX_CKPT_FILE")
    selected = model or IMAGE_BACKEND
    return _MODEL_CKPT_MAP.get(selected, "flux1-schnell.safetensors")


@mcp.tool()
async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    cfg: float = 1.0,
    negative_prompt: str = "",
    seed: int = -1,
    model: str = "flux",
) -> dict:
    """
    Generate an image using FLUX.1 or SDXL via ComfyUI.
    Returns a URL to the generated image file.

    Args:
        prompt: Text description of the image to generate
        width: Image width in pixels (default 1024)
        height: Image height in pixels (default 1024)
        steps: Number of diffusion steps (FLUX default 4, SDXL default 25)
        cfg: CFG scale (FLUX default 1.0, SDXL default 7.5)
        negative_prompt: Things to avoid in the image (SDXL only)
        seed: Random seed, -1 for random
        model: Model to use - 'flux' (fast), 'flux-uncensored' (uncensored),
               'sdxl' (high quality). Defaults to 'flux'.
    """
    if seed == -1:
        seed = int(time.time() * 1000) % (2**32)

    workflow = _get_workflow(model)
    selected_model = model or IMAGE_BACKEND

    if selected_model == "sdxl":
        # SDXL: bundled checkpoint — CheckpointLoaderSimple provides model+clip+vae.
        # Node map: 1=CheckpointLoaderSimple, 2=CLIPTextEncode+, 3=CLIPTextEncode-,
        #           4=EmptyLatentImage, 5=KSampler, 6=VAEDecode, 7=SaveImage
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["text"] = negative_prompt
        workflow["4"]["inputs"]["width"] = width
        workflow["4"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["seed"] = seed
        workflow["5"]["inputs"]["steps"] = min(max(steps, 1), 50)
        workflow["5"]["inputs"]["cfg"] = min(max(cfg, 1), 20)
    else:
        # FLUX / flux-uncensored: split-loader node map (see FLUX_WORKFLOW definition):
        #   1=CheckpointLoaderSimple(UNet), 2=DualCLIPLoader, 3=VAELoader,
        #   4=CLIPTextEncode+, 5=CLIPTextEncode-, 6=EmptyLatentImage,
        #   7=FluxGuidance, 8=KSampler, 9=VAEDecode, 10=SaveImage
        workflow["4"]["inputs"]["text"] = prompt
        workflow["5"]["inputs"]["text"] = negative_prompt or ""
        workflow["6"]["inputs"]["width"] = width
        workflow["6"]["inputs"]["height"] = height
        workflow["8"]["inputs"]["seed"] = seed
        workflow["8"]["inputs"]["steps"] = min(max(steps, 1), 20)
        workflow["8"]["inputs"]["cfg"] = min(max(cfg, 0), 10)
        # Checkpoint (UNet), CLIP, and VAE filenames from env vars with installed defaults
        workflow["1"]["inputs"]["ckpt_name"] = _get_checkpoint(model)
        workflow["2"]["inputs"]["clip_name1"] = os.getenv(
            "FLUX_CLIP_L_FILE", "text_encoder/model.safetensors"
        )
        workflow["2"]["inputs"]["clip_name2"] = os.getenv(
            "FLUX_CLIP_T5_FILE", "text_encoder_2/model-00001-of-00002.safetensors"
        )
        workflow["3"]["inputs"]["vae_name"] = os.getenv("FLUX_VAE_FILE", "ae.safetensors")

    client_id = str(uuid.uuid4())

    client = await _get_client()
    # Queue the prompt
    try:
        resp = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        resp.raise_for_status()
    except httpx.ConnectError as e:
        return {
            "success": False,
            "error": (
                f"ComfyUI not available at {COMFYUI_URL}: {e}. "
                "Ensure ComfyUI is running and a model is installed."
            ),
        }
    except httpx.HTTPStatusError as e:
        # Return the actual ComfyUI error message for non-2xx responses
        try:
            error_detail = e.response.json().get("error", e.response.text[:200])
        except Exception:
            error_detail = e.response.text[:200] if e.response.text else str(e)
        return {
            "success": False,
            "error": f"ComfyUI rejected workflow (HTTP {e.response.status_code}): {error_detail}",
        }
    prompt_id = resp.json()["prompt_id"]

    # Poll for completion (SDXL at 25 steps can take 5+ min on MPS)
    poll_interval = 1
    max_polls = COMFYUI_TIMEOUT // poll_interval
    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)
        history_resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
        history = history_resp.json()

        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for _node_id, node_output in outputs.items():
                images = node_output.get("images", [])
                if images:
                    filename = images[0]["filename"]
                    return {
                        "success": True,
                        "filename": filename,
                        "url": f"{COMFYUI_URL}/view?filename={filename}&type=output",
                        "prompt": prompt,
                        "seed": seed,
                    }

    return {
        "success": False,
        "error": f"Generation timed out after {COMFYUI_TIMEOUT // 60} minutes",
    }


@mcp.tool()
async def list_workflows() -> list[str]:
    """List available ComfyUI workflow checkpoints."""
    client = await _get_client()
    try:
        resp = await client.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple")
        resp.raise_for_status()
        data = resp.json()
        checkpoints = (
            data.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [[]])[0]
        )
        return checkpoints if isinstance(checkpoints, list) else []
    except Exception:
        return []


@mcp.tool()
async def get_generation_status(job_id: str) -> dict:
    """Check the status of an image generation job by its prompt_id.

    Args:
        job_id: The prompt_id returned by generate_image
    """
    client = await _get_client()
    try:
        resp = await client.get(f"{COMFYUI_URL}/history/{job_id}")
        if resp.status_code == 200:
            history = resp.json()
            if job_id in history:
                return {
                    "status": "complete",
                    "job_id": job_id,
                    "outputs": history[job_id].get("outputs", {}),
                }
            return {"status": "pending", "job_id": job_id}
        return {"status": "unknown", "job_id": job_id, "http": resp.status_code}
    except Exception as e:
        return {"error": str(e), "job_id": job_id}


if __name__ == "__main__":
    port = int(os.getenv("COMFYUI_MCP_PORT", "8910"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    try:
        mcp.run(transport="streamable-http")
    finally:
        # Clean up shared httpx client on shutdown
        asyncio.run(_close_client())
