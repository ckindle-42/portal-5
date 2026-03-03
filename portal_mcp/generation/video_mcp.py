"""
Video Generation MCP Server
Wraps ComfyUI video workflows for local video generation.
Exposes: generate_video, list_video_models

Requires: ComfyUI running at COMFYUI_URL with a video model installed
          (CogVideoX, Wan2.2, or Mochi via ComfyUI Manager)
Start with: python -m mcp.generation.video_mcp
"""

import asyncio
import json
import os
import time
import uuid

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

mcp = FastMCP("video-generation")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    return JSONResponse({"status": "ok", "service": "video-mcp"})


# Tool manifest for discovery
TOOLS_MANIFEST = [
    {
        "name": "generate_video",
        "description": "Generate a video using ComfyUI with a local video model (Wan2.2 or CogVideoX)",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text description of the video to generate"},
                "width": {"type": "integer", "description": "Video width in pixels", "default": 832},
                "height": {"type": "integer", "description": "Video height in pixels", "default": 480},
                "frames": {"type": "integer", "description": "Number of frames", "default": 81},
                "fps": {"type": "integer", "description": "Frames per second", "default": 16},
                "steps": {"type": "integer", "description": "Number of inference steps", "default": 20},
                "cfg": {"type": "number", "description": "CFG scale", "default": 6.0},
                "negative_prompt": {"type": "string", "description": "Negative prompt", "default": ""},
                "model": {"type": "string", "description": "Model name (optional)"},
                "seed": {"type": "integer", "description": "Random seed", "default": -1},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "list_video_models",
        "description": "List available video model checkpoints in ComfyUI",
        "parameters": {"type": "object", "properties": {}},
    },
]


@mcp.custom_route("/tools", methods=["GET"])
async def list_tools(request):
    return JSONResponse({"tools": TOOLS_MANIFEST})

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
VIDEO_BACKEND = os.getenv("VIDEO_BACKEND", "wan22")  # "wan22" or "cogvideox"

# Wan2.2 T2V workflow — uses UNETLoader, CLIPLoader, VAELoader, EmptyHunyuanLatentVideo
_WAN22_T2V_WORKFLOW: dict = {
    "1": {
        "inputs": {"model_name": "wan2.2_ti2v_5B_fp16.safetensors"},
        "class_type": "UNETLoader",
    },
    "2": {
        "inputs": {"model_name": "clip_l.safetensors"},
        "class_type": "CLIPLoader",
    },
    "3": {
        "inputs": {"model_name": "wan2.2_vae.safetensors"},
        "class_type": "VAELoader",
    },
    "4": {
        "inputs": {"text": "", "clip": ["2", 1]},
        "class_type": "CLIPTextEncode",
    },
    "5": {
        "inputs": {"text": "", "clip": ["2", 1]},
        "class_type": "CLIPTextEncode",
    },
    "6": {
        "inputs": {
            "width": 832,
            "height": 480,
            "video_frames": 81,
            "batch_size": 1,
        },
        "class_type": "EmptyHunyuanLatentVideo",
    },
    "7": {
        "inputs": {
            "model": ["1", 0],
            "positive": ["4", 0],
            "negative": ["5", 0],
            "latent_image": ["6", 0],
            "seed": 42,
            "steps": 20,
            "cfg": 6.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
        },
        "class_type": "KSampler",
    },
    "8": {
        "inputs": {"samples": ["7", 0], "vae": ["3", 0]},
        "class_type": "VAEDecode",
    },
    "9": {
        "inputs": {
            "filename_prefix": "portal_video_",
            "images": ["8", 0],
            "fps": 16,
            "format": "video/h264-mp4",
        },
        "class_type": "VHS_VideoCombine",
    },
}

# CogVideoX fallback workflow — works with cogvideox_5b.safetensors
_COGVIDEOX_WORKFLOW: dict = {
    "1": {
        "inputs": {"ckpt_name": "cogvideox_5b.safetensors"},
        "class_type": "CheckpointLoaderSimple",
    },
    "2": {
        "inputs": {"text": "", "clip": ["1", 1]},
        "class_type": "CLIPTextEncode",
    },
    "3": {
        "inputs": {"width": 720, "height": 480, "video_frames": 49, "batch_size": 1},
        "class_type": "EmptyLatentVideo",
    },
    "4": {
        "inputs": {
            "model": ["1", 0],
            "conditioning": ["2", 0],
            "latent_image": ["3", 0],
            "noise_seed": 42,
            "steps": 20,
            "cfg": 6,
            "sampler_name": "euler",
            "scheduler": "linear",
            "denoise": 1,
        },
        "class_type": "KSampler",
    },
    "5": {
        "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
        "class_type": "VAEDecode",
    },
    "6": {
        "inputs": {
            "filename_prefix": "portal_video_",
            "images": ["5", 0],
            "fps": 8,
            "format": "video/h264-mp4",
        },
        "class_type": "VHS_VideoCombine",
    },
}


def _get_workflow() -> dict:
    """Get the workflow based on VIDEO_BACKEND env var."""
    if VIDEO_BACKEND == "cogvideox":
        return _COGVIDEOX_WORKFLOW.copy()
    return _WAN22_T2V_WORKFLOW.copy()


@mcp.tool()
async def generate_video(
    prompt: str,
    width: int = 832,
    height: int = 480,
    frames: int = 81,
    fps: int = 16,
    steps: int = 20,
    cfg: float = 6.0,
    negative_prompt: str = "",
    model: str = "",
    seed: int = -1,
) -> dict:
    """
    Generate a video using ComfyUI with a local video model (Wan2.2 or CogVideoX).

    Returns a URL to the generated video served by ComfyUI.

    Args:
        prompt: Text description of the video to generate
        width: Video width in pixels (default 832)
        height: Video height in pixels (default 480)
        frames: Number of frames (default 81, ≈5s at 16fps)
        fps: Output frames per second (default 16)
        steps: Diffusion inference steps (default 20)
        cfg: CFG scale (default 6.0)
        negative_prompt: Things to avoid in the video
        model: Override model name (optional, auto-detected from backend)
        seed: Random seed, -1 for random
    """
    if seed == -1:
        seed = int(time.time() * 1000) % (2**32)

    workflow = _get_workflow()

    # Apply workflow-specific parameters
    if VIDEO_BACKEND == "cogvideox":
        # Use model param or default
        model_name = model if model else "cogvideox_5b.safetensors"
        workflow["1"]["inputs"]["ckpt_name"] = model_name
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["width"] = width
        workflow["3"]["inputs"]["height"] = height
        workflow["3"]["inputs"]["video_frames"] = frames
        workflow["4"]["inputs"]["noise_seed"] = seed
        workflow["4"]["inputs"]["steps"] = steps
        workflow["4"]["inputs"]["cfg"] = cfg
        workflow["6"]["inputs"]["fps"] = fps
    else:
        # Wan2.2 workflow
        if model:
            workflow["1"]["inputs"]["model_name"] = model
        workflow["4"]["inputs"]["text"] = prompt
        workflow["5"]["inputs"]["text"] = negative_prompt
        workflow["6"]["inputs"]["width"] = width
        workflow["6"]["inputs"]["height"] = height
        workflow["6"]["inputs"]["video_frames"] = frames
        workflow["7"]["inputs"]["seed"] = seed
        workflow["7"]["inputs"]["steps"] = steps
        workflow["7"]["inputs"]["cfg"] = cfg
        workflow["9"]["inputs"]["fps"] = fps

    client_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            resp = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPStatusError) as e:
            return {
                "success": False,
                "error": (
                    f"ComfyUI not available at {COMFYUI_URL}: {e}. "
                    "Install a video model via ComfyUI Manager (Wan2.2 or CogVideoX)."
                ),
            }

        prompt_id = resp.json()["prompt_id"]

        # Poll for completion (video generation takes 2–10 minutes)
        for _ in range(300):  # 300 × 2s = 10 min max
            await asyncio.sleep(2)
            history_resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            history = history_resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_output in outputs.values():
                    gifs = node_output.get("gifs", [])
                    if gifs:
                        filename = gifs[0]["filename"]
                        return {
                            "success": True,
                            "filename": filename,
                            "url": f"{COMFYUI_URL}/view?filename={filename}&type=output",
                            "prompt": prompt,
                            "seed": seed,
                            "frames": frames,
                            "fps": fps,
                        }
                return {
                    "success": False,
                    "error": "Generation completed but no video output found. Check ComfyUI logs.",
                }

    return {"success": False, "error": "Video generation timed out after 10 minutes"}


@mcp.tool()
async def list_video_models() -> list[str]:
    """List available video model checkpoints in ComfyUI."""
    video_keywords = ("cogvideo", "mochi", "wan2", "wan_2", "video")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            all_checkpoints: list[str] = []

            # Check for Wan2.2 models (UNETLoader)
            try:
                resp = await client.get(f"{COMFYUI_URL}/object_info/UNETLoader")
                data = resp.json()
                checkpoints = (
                    data.get("UNETLoader", {})
                    .get("input", {})
                    .get("required", {})
                    .get("model_name", [[]])[0]
                )
                if checkpoints:
                    all_checkpoints.extend(checkpoints)
            except Exception:
                pass  # UNETLoader not available

            # Check for CogVideoX models (CheckpointLoaderSimple)
            try:
                resp = await client.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple")
                data = resp.json()
                checkpoints = (
                    data.get("CheckpointLoaderSimple", {})
                    .get("input", {})
                    .get("required", {})
                    .get("ckpt_name", [[]])[0]
                )
                if checkpoints:
                    all_checkpoints.extend(checkpoints)
            except Exception:
                pass  # CheckpointLoaderSimple not available

            # Filter to likely video models
            video_models = [c for c in all_checkpoints if any(k in c.lower() for k in video_keywords)]
            return video_models if video_models else all_checkpoints
        except Exception as e:
            return [f"Error listing models: {e}"]


if __name__ == "__main__":
    port = int(os.getenv("VIDEO_MCP_PORT", "8911"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")
