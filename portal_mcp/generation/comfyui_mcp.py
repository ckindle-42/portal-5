"""
ComfyUI MCP Server
Wraps the ComfyUI workflow API as MCP tools.
Exposes: generate_image, list_workflows, get_generation_status

Requires: ComfyUI running at COMFYUI_URL (default :8188)
Start with: python -m mcp.generation.comfyui_mcp
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("comfyui-generation")


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
                "prompt": {"type": "string", "description": "Text description of the image to generate"},
                "width": {"type": "integer", "description": "Image width in pixels", "default": 1024},
                "height": {"type": "integer", "description": "Image height in pixels", "default": 1024},
                "steps": {"type": "integer", "description": "Number of diffusion steps", "default": 4},
                "cfg": {"type": "number", "description": "CFG scale", "default": 1.0},
                "negative_prompt": {"type": "string", "description": "Negative prompt", "default": ""},
                "seed": {"type": "integer", "description": "Random seed (-1 for random)", "default": -1},
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
IMAGE_BACKEND = os.getenv("IMAGE_BACKEND", "flux")  # "flux" or "sdxl"
OUTPUT_DIR = Path.home() / "AI_Output" / "images"

# FLUX.1-schnell workflow template
FLUX_WORKFLOW = {
    "6": {"inputs": {"text": "", "clip": ["30", 1]}, "class_type": "CLIPTextEncode"},
    "8": {"inputs": {"samples": ["31", 0], "vae": ["30", 2]}, "class_type": "VAEDecode"},
    "9": {"inputs": {"filename_prefix": "portal_", "images": ["8", 0]}, "class_type": "SaveImage"},
    "27": {
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        "class_type": "EmptySD3LatentImage",
    },
    "30": {
        "inputs": {"ckpt_name": "flux1-schnell.safetensors"},
        "class_type": "CheckpointLoaderSimple",
    },
    "31": {
        "inputs": {
            "model": ["30", 0],
            "conditioning": ["6", 0],
            "latent_image": ["27", 0],
            "noise_seed": 42,
            "steps": 4,
            "cfg": 1,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
}

# SDXL workflow template - uses EmptyLatentImage and has negative prompt
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
            "noise_seed": 42,
            "steps": 25,
            "cfg": 7.5,
            "sampler_name": "dpmpp_2m_karras",
            "scheduler": "normal",
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
    "6": {"inputs": {"samples": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
    "7": {"inputs": {"filename_prefix": "portal_", "images": ["6", 0]}, "class_type": "SaveImage"},
}


def _get_workflow() -> dict:
    """Get the workflow based on IMAGE_BACKEND env var."""
    if IMAGE_BACKEND == "sdxl":
        return SDXL_WORKFLOW.copy()
    return FLUX_WORKFLOW.copy()


@mcp.tool()
async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    cfg: float = 1.0,
    negative_prompt: str = "",
    seed: int = -1,
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
    """
    if seed == -1:
        seed = int(time.time() * 1000) % (2**32)

    workflow = _get_workflow()

    if IMAGE_BACKEND == "sdxl":
        # SDXL uses different node IDs and has negative prompt
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["text"] = negative_prompt
        workflow["4"]["inputs"]["width"] = width
        workflow["4"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["noise_seed"] = seed
        workflow["5"]["inputs"]["steps"] = min(max(steps, 1), 50)
        workflow["5"]["inputs"]["cfg"] = min(max(cfg, 1), 20)
    else:
        # FLUX workflow
        workflow["6"]["inputs"]["text"] = prompt
        workflow["27"]["inputs"]["width"] = width
        workflow["27"]["inputs"]["height"] = height
        workflow["31"]["inputs"]["noise_seed"] = seed
        workflow["31"]["inputs"]["steps"] = min(max(steps, 1), 20)
        workflow["31"]["inputs"]["cfg"] = min(max(cfg, 0), 10)

    client_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Queue the prompt
        resp = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]

        # Poll for completion
        for _ in range(120):  # 120 × 1s = 2 min max
            await asyncio.sleep(1)
            history_resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            history = history_resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    images = node_output.get("images", [])
                    if images:
                        filename = images[0]["filename"]
                        return {
                            "success": True,
                            "filename": filename,
                            "url": f"http://localhost:8080/images/{filename}",
                            "prompt": prompt,
                            "seed": seed,
                        }

        return {"success": False, "error": "Generation timed out after 2 minutes"}


@mcp.tool()
async def list_workflows() -> list[str]:
    """List available ComfyUI workflow checkpoints."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple")
        data = resp.json()
        checkpoints = (
            data.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [[]])[0]
        )
        return checkpoints


if __name__ == "__main__":
    port = int(os.getenv("COMFYUI_MCP_PORT", "8910"))
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
