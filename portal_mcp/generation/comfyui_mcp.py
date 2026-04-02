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

# Module-level httpx client — created once per process, reused for all requests.
# Eliminates TCP/TLS handshake overhead on every image generation call (P9).
_http_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=120.0, limits=httpx.Limits(max_connections=5))
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

# FLUX.1 workflow — uses CheckpointLoaderSimple for bundled checkpoints.
# CheckpointLoaderSimple loads a bundled .safetensors that contains the full
# FLUX model (UNet + CLIP encoders in one file). This is the standard format
# for official FLUX.1 models on HuggingFace.
# Node layout (ComfyUI v0.16):
#   1: CheckpointLoaderSimple → model[0], clip[1], vae[2]
#   2: CLIPTextEncode (positive) → conditioning[0]  ← clip from [1,1]
#   3: CLIPTextEncode (negative) → conditioning[0]  ← clip from [1,1]; empty text
#   4: EmptyLatentImage  → latent[0]
#   5: FluxGuidance     → conditioning[0]  ← takes positive conditioning + guidance value
#   6: KSampler        → latent[0]  ← uses model[0], positive=[5,0], negative=[3,0]
#   7: VAEDecode       → image[0]  ← samples from [6,0], vae from [1,2]
#   8: SaveImage
# ComfyUI v0.16: node IDs must be strings; connections as [node_id, output_index].
FLUX_WORKFLOW = {
    "1": {
        # ckpt_name is set dynamically at runtime via _get_checkpoint()
        "inputs": {"ckpt_name": "__FLUX_CKPT__"},
        "class_type": "CheckpointLoaderSimple",
    },
    "2": {
        "inputs": {"text": "", "clip": ["1", 1]},
        "class_type": "CLIPTextEncode",
    },
    "3": {
        # Empty negative conditioning — KSampler requires a conditioning tensor,
        # not a raw string or empty string. FLUX processes negative conditioning
        # differently from SD but the node graph must wire a valid CLIPTextEncode output.
        "inputs": {"text": "", "clip": ["1", 1]},
        "class_type": "CLIPTextEncode",
    },
    "4": {
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "5": {
        "inputs": {"conditioning": ["2", 0], "guidance": 3.5},
        "class_type": "FluxGuidance",
    },
    "6": {
        "inputs": {
            "seed": 42,
            "steps": 4,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
            "model": ["1", 0],
            "positive": ["5", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
    "7": {
        "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        "class_type": "VAEDecode",
    },
    "8": {
        "inputs": {"filename_prefix": "portal_", "images": ["7", 0]},
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
    """Get the workflow based on model selection.

    Args:
        model: Model name ('flux', 'flux-uncensored', 'sdxl') or None to use IMAGE_BACKEND env var.
    """
    selected = model or IMAGE_BACKEND
    if selected == "sdxl":
        return SDXL_WORKFLOW.copy()
    return FLUX_WORKFLOW.copy()


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
        # SDXL uses different node IDs and has negative prompt
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["text"] = negative_prompt
        workflow["4"]["inputs"]["width"] = width
        workflow["4"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["seed"] = seed
        workflow["5"]["inputs"]["steps"] = min(max(steps, 1), 50)
        workflow["5"]["inputs"]["cfg"] = min(max(cfg, 1), 20)
    else:
        # FLUX / flux-uncensored node map (see FLUX_WORKFLOW definition):
        #   2 = CLIPTextEncode (positive), 3 = CLIPTextEncode (negative),
        #   4 = EmptyLatentImage, 5 = FluxGuidance, 6 = KSampler
        workflow["2"]["inputs"]["text"] = prompt   # positive CLIPTextEncode
        workflow["3"]["inputs"]["text"] = negative_prompt or ""
        workflow["4"]["inputs"]["width"] = width
        workflow["4"]["inputs"]["height"] = height
        workflow["6"]["inputs"]["seed"] = seed
        workflow["6"]["inputs"]["steps"] = min(max(steps, 1), 20)
        workflow["6"]["inputs"]["cfg"] = min(max(cfg, 0), 10)
        # Set checkpoint filename based on selected model
        workflow["1"]["inputs"]["ckpt_name"] = _get_checkpoint(model)

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

    # Poll for completion
    for _ in range(120):  # 120 × 1s = 2 min max
        await asyncio.sleep(1)
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

    return {"success": False, "error": "Generation timed out after 2 minutes"}


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
