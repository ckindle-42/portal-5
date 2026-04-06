"""
Video Generation MCP Server
Wraps ComfyUI video workflows for local video generation.
Exposes: generate_video, list_video_models

Requires: ComfyUI running at COMFYUI_URL with a video model installed
          (CogVideoX, Wan2.2, or Mochi via ComfyUI Manager)
Start with: python -m mcp.generation.video_mcp
"""

import asyncio
import logging
import os
import time
import uuid

import httpx
from starlette.responses import JSONResponse

from portal_mcp.mcp_server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("video-generation")

# Module-level httpx client — created once per process, reused for all requests.
# Eliminates TCP/TLS handshake overhead on every video generation call (P9).
_http_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=600.0, limits=httpx.Limits(max_connections=5))
    return _http_client


async def _close_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


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
                "prompt": {
                    "type": "string",
                    "description": "Text description of the video to generate",
                },
                "width": {
                    "type": "integer",
                    "description": "Video width in pixels",
                    "default": 832,
                },
                "height": {
                    "type": "integer",
                    "description": "Video height in pixels",
                    "default": 480,
                },
                "frames": {"type": "integer", "description": "Number of frames", "default": 81},
                "fps": {"type": "integer", "description": "Frames per second", "default": 16},
                "steps": {
                    "type": "integer",
                    "description": "Number of inference steps",
                    "default": 20,
                },
                "cfg": {"type": "number", "description": "CFG scale", "default": 6.0},
                "negative_prompt": {
                    "type": "string",
                    "description": "Negative prompt",
                    "default": "",
                },
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

# Video model filename — single-file model in models/diffusion_models/.
# Default: HunyuanVideo merged single-file (hunyuanvideo_comfyui.safetensors symlink →
# models/video/diffusion_pytorch_model_comfyui.safetensors).
# Override with VIDEO_MODEL_FILE env var to use a different model.
#
# Required ComfyUI model files for HunyuanVideo T2V:
#   models/diffusion_models/hunyuanvideo_comfyui.safetensors  (~24GB transformer)
#   models/text_encoders/llava_llama3_fp8_scaled.safetensors  (~8.9GB text encoder)
#   models/text_encoders/clip_l.safetensors                   (~235MB CLIP-L)
#   models/vae/hunyuan_video_vae_bf16.safetensors             (~200MB VAE)
#
# Download missing models from:
#   huggingface-cli download Comfy-Org/HunyuanVideo_repackaged \
#     --include "split_files/text_encoders/llava_llama3_fp8_scaled.safetensors" \
#     --local-dir ~/ComfyUI/models
#   huggingface-cli download Comfy-Org/HunyuanVideo_repackaged \
#     --include "split_files/vae/hunyuan_video_vae_bf16.safetensors" \
#     --local-dir ~/ComfyUI/models
VIDEO_MODEL_FILE = os.getenv(
    "VIDEO_MODEL_FILE",
    "hunyuanvideo_comfyui.safetensors",
)

# HunyuanVideo T2V workflow — official ComfyUI node layout.
# Matches the ComfyUI example workflow for HunyuanVideo T2V.
# KSampler is NOT compatible with HunyuanVideo; use SamplerCustomAdvanced + FluxGuidance.
# Node layout:
#   1: UNETLoader → model[0]
#   2: DualCLIPLoader(clip_l, llava_llama3, type="hunyuan_video") → clip[0]
#   3: VAELoader → vae[0]
#   4: CLIPTextEncode (positive prompt) → conditioning[0]
#   5: EmptyHunyuanLatentVideo → latent[0]
#   6: ModelSamplingSD3(shift=7) → model[0]
#   7: KSamplerSelect(euler) → sampler[0]
#   8: BasicScheduler(simple, steps, denoise) → sigmas[0]
#   9: RandomNoise(seed) → noise[0]
#  10: FluxGuidance(guidance) → conditioning[0]
#  11: BasicGuider(model, conditioning) → guider[0]
#  12: SamplerCustomAdvanced → latent[0]
#  13: VAEDecodeTiled(tile_size=256) → image[0]  (batch of frames)
#  14: CreateVideo → video[0]
#  15: SaveVideo
_WAN22_T2V_WORKFLOW: dict = {
    "1": {
        "inputs": {"unet_name": VIDEO_MODEL_FILE, "weight_dtype": "default"},
        "class_type": "UNETLoader",
    },
    "2": {
        "inputs": {
            # clip_name1: CLIP-L (already present as hunyuan-clip/model.safetensors)
            # clip_name2: LLaVA LLaMA3 (download from Comfy-Org/HunyuanVideo_repackaged)
            "clip_name1": os.getenv("HUNYUAN_CLIP_L", "hunyuan-clip/model.safetensors"),
            "clip_name2": os.getenv("HUNYUAN_LLAVA", "llava_llama3_fp8_scaled.safetensors"),
            "type": "hunyuan_video",
        },
        "class_type": "DualCLIPLoader",
    },
    "3": {
        "inputs": {"vae_name": os.getenv("HUNYUAN_VAE", "hunyuan_video_vae_bf16.safetensors")},
        "class_type": "VAELoader",
    },
    "4": {
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
    "5": {
        "inputs": {
            "width": 848,
            "height": 480,
            "length": 73,
            "batch_size": 1,
        },
        "class_type": "EmptyHunyuanLatentVideo",
    },
    "6": {
        "inputs": {"model": ["1", 0], "shift": 7.0},
        "class_type": "ModelSamplingSD3",
    },
    "7": {
        "inputs": {"sampler_name": "euler"},
        "class_type": "KSamplerSelect",
    },
    "8": {
        "inputs": {
            "model": ["6", 0],
            "scheduler": "simple",
            "steps": 20,
            "denoise": 1.0,
        },
        "class_type": "BasicScheduler",
    },
    "9": {
        "inputs": {"noise_seed": 1},
        "class_type": "RandomNoise",
    },
    "10": {
        "inputs": {"conditioning": ["4", 0], "guidance": 6.0},
        "class_type": "FluxGuidance",
    },
    "11": {
        "inputs": {"model": ["6", 0], "conditioning": ["10", 0]},
        "class_type": "BasicGuider",
    },
    "12": {
        "inputs": {
            "noise": ["9", 0],
            "guider": ["11", 0],
            "sampler": ["7", 0],
            "sigmas": ["8", 0],
            "latent_image": ["5", 0],
        },
        "class_type": "SamplerCustomAdvanced",
    },
    "13": {
        "inputs": {
            "samples": ["12", 0],
            "vae": ["3", 0],
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
        "class_type": "VAEDecodeTiled",
    },
    "14": {
        "inputs": {"images": ["13", 0], "fps": 24.0},
        "class_type": "CreateVideo",
    },
    "15": {
        "inputs": {
            "video": ["14", 0],
            "filename_prefix": "portal_video_",
            "format": "auto",
            "codec": "auto",
        },
        "class_type": "SaveVideo",
    },
}

# CogVideoX fallback workflow — uses CheckpointLoaderSimple + EmptyMochiLatentVideo
# EmptyMochiLatentVideo uses "length" parameter (v0.16.3).
# KSampler uses "seed" (not "noise_seed") and "normal" scheduler in v0.16.3.
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
        "inputs": {"width": 720, "height": 480, "length": 49, "batch_size": 1},
        "class_type": "EmptyMochiLatentVideo",
    },
    "4": {
        "inputs": {
            "model": ["1", 0],
            "positive": ["2", 0],
            "negative": ["2", 0],
            "latent_image": ["3", 0],
            "seed": 42,
            "steps": 20,
            "cfg": 6,
            "sampler_name": "euler",
            "scheduler": "normal",
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
            "pingpong": False,
            "save_output": True,
        },
        "class_type": "VHS_VideoCombine",
    },
}


def _get_workflow() -> dict:
    """Get a deep copy of the workflow based on VIDEO_BACKEND env var."""
    import copy
    if VIDEO_BACKEND == "cogvideox":
        return copy.deepcopy(_COGVIDEOX_WORKFLOW)
    return copy.deepcopy(_WAN22_T2V_WORKFLOW)


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
        # CogVideoX: CheckpointLoaderSimple(1), CLIPTextEncode(2),
        # EmptyMochiLatentVideo(3), KSampler(4), VAEDecode(5), VHS_VideoCombine(6)
        model_name = model if model else "cogvideox_5b.safetensors"
        workflow["1"]["inputs"]["ckpt_name"] = model_name
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["width"] = width
        workflow["3"]["inputs"]["height"] = height
        workflow["3"]["inputs"]["length"] = frames
        workflow["4"]["inputs"]["seed"] = seed
        workflow["4"]["inputs"]["steps"] = steps
        workflow["4"]["inputs"]["cfg"] = cfg
        workflow["6"]["inputs"]["fps"] = fps
    else:
        # HunyuanVideo: UNETLoader(1), DualCLIPLoader(2), VAELoader(3),
        # CLIPTextEncode(4), EmptyHunyuanLatentVideo(5), ModelSamplingSD3(6),
        # KSamplerSelect(7), BasicScheduler(8), RandomNoise(9), FluxGuidance(10),
        # BasicGuider(11), SamplerCustomAdvanced(12), VAEDecodeTiled(13),
        # CreateVideo(14), SaveVideo(15)
        if model:
            workflow["1"]["inputs"]["unet_name"] = model
        workflow["4"]["inputs"]["text"] = prompt
        workflow["5"]["inputs"]["width"] = width
        workflow["5"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["length"] = frames
        workflow["8"]["inputs"]["steps"] = steps
        workflow["9"]["inputs"]["noise_seed"] = seed
        workflow["10"]["inputs"]["guidance"] = cfg
        workflow["14"]["inputs"]["fps"] = float(fps)

    client_id = str(uuid.uuid4())

    client = await _get_client()
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
                "Ensure ComfyUI is running."
            ),
        }
    except httpx.HTTPStatusError as e:
        try:
            error_detail = e.response.json().get("error", e.response.text[:200])
        except Exception:
            error_detail = e.response.text[:200] if e.response.text else str(e)
        return {
            "success": False,
            "error": f"ComfyUI rejected workflow (HTTP {e.response.status_code}): {error_detail}",
        }

    prompt_id = resp.json()["prompt_id"]

    # Poll for completion (video generation takes 2–10 minutes)
    for _ in range(300):  # 300 × 2s = 10 min max
        await asyncio.sleep(2)
        history_resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
        history = history_resp.json()

        if prompt_id in history:
            entry = history[prompt_id]
            status_str = entry.get("status", {}).get("status_str", "unknown")

            # Surface ComfyUI error messages directly
            if status_str == "error":
                msgs = entry.get("status", {}).get("messages", [])
                for msg in reversed(msgs):
                    if isinstance(msg, list) and msg[0] == "execution_error":
                        err = msg[1] if len(msg) > 1 else {}
                        return {
                            "success": False,
                            "error": (
                                f"ComfyUI error in {err.get('node_type','?')} "
                                f"(node {err.get('node_id','?')}): "
                                f"{err.get('exception_message','unknown error')}"
                            ),
                        }
                return {"success": False, "error": "ComfyUI workflow failed (unknown error)"}

            outputs = entry.get("outputs", {})
            for node_output in outputs.values():
                # SaveVideo outputs "videos"; VHS_VideoCombine uses "gifs"
                video_files = (
                    node_output.get("videos")
                    or node_output.get("gifs")
                    or []
                )
                if video_files and isinstance(video_files, list) and len(video_files) > 0:
                    filename = (
                        video_files[0].get("filename")
                        if isinstance(video_files[0], dict)
                        else str(video_files[0])
                    )
                    if filename:
                        return {
                            "success": True,
                            "filename": filename,
                            "url": f"{COMFYUI_URL}/view?filename={filename}&type=output",
                            "prompt": prompt,
                            "seed": seed,
                            "frames": frames,
                            "fps": fps,
                        }
            logger.debug(
                "ComfyUI history for prompt_id=%s had no video output. history=%s",
                prompt_id,
                history.get(prompt_id),
            )
            return {
                "success": False,
                "error": "Generation completed but no video output found. Check ComfyUI logs.",
            }

    return {"success": False, "error": "Video generation timed out after 10 minutes"}


@mcp.tool()
async def list_video_models() -> list[str]:
    """List available video model checkpoints in ComfyUI."""
    video_keywords = ("cogvideo", "mochi", "wan2", "wan_2", "hunyuan", "video", "remix", "ltxv")

    client = await _get_client()
    try:
        all_models: list[str] = []

        # UNETLoader: HunyuanVideo, Wan2.2 etc. (models/diffusion_models/)
        try:
            resp = await client.get(f"{COMFYUI_URL}/object_info/UNETLoader")
            data = resp.json()
            models = (
                data.get("UNETLoader", {})
                .get("input", {})
                .get("required", {})
                .get("model_name", [[]])[0]
            )
            if models:
                # Return unique directory prefixes (model names, not shard filenames)
                seen = set()
                for m in models:
                    name = m.split("/")[0] if "/" in m else m
                    if name not in seen:
                        seen.add(name)
                        all_models.append(name)
        except Exception:
            pass

        # DiffusersLoader: video/wan2.2 paths (models/diffusers/ subdirs)
        try:
            resp = await client.get(f"{COMFYUI_URL}/object_info/DiffusersLoader")
            data = resp.json()
            paths = (
                data.get("DiffusersLoader", {})
                .get("input", {})
                .get("required", {})
                .get("model_path", [[]])[0]
            )
            if paths:
                all_models.extend(p for p in paths if any(k in p.lower() for k in video_keywords))
        except Exception:
            pass

        # Filter to likely video models
        video_models = [m for m in all_models if any(k in m.lower() for k in video_keywords)]
        return video_models if video_models else all_models
    except Exception as e:
        return [f"Error listing models: {e}"]


if __name__ == "__main__":
    port = int(os.getenv("VIDEO_MCP_PORT", "8911"))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    try:
        mcp.run(transport="streamable-http")
    finally:
        asyncio.run(_close_client())
