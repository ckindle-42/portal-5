"""
ComfyUI MCP Server
Wraps the ComfyUI workflow API as MCP tools.
Exposes: generate_image, start_image_generation, get_image_status, get_latest_images,
         list_workflows, get_generation_status

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

mcp = FastMCP("comfyui-generation", host="0.0.0.0")

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
        "name": "start_image_generation",
        "description": (
            "Start image generation and return immediately with a job_id. "
            "Use this for OWUI/chat — generation takes 1-40 min depending on model. "
            "Follow up with get_image_status(job_id) to retrieve the result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text description of the image"},
                "model": {
                    "type": "string",
                    "description": "Model: 'flux' (schnell, fast), 'flux-uncensored', 'sdxl'",
                    "default": "flux",
                },
                "width": {"type": "integer", "default": 1024},
                "height": {"type": "integer", "default": 1024},
                "steps": {"type": "integer", "default": 4},
                "cfg": {"type": "number", "default": 1.0},
                "negative_prompt": {"type": "string", "default": ""},
                "seed": {"type": "integer", "default": -1},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "get_image_status",
        "description": "Check status of an image generation job. Returns URL when complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "job_id from start_image_generation"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "get_latest_images",
        "description": "Get the most recently generated images from ComfyUI.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of images to return", "default": 5},
            },
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Generate an image and block until complete. WARNING: takes 1-40 minutes. "
            "Prefer start_image_generation for interactive use."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "model": {"type": "string", "default": "flux"},
                "width": {"type": "integer", "default": 1024},
                "height": {"type": "integer", "default": 1024},
                "steps": {"type": "integer", "default": 4},
                "cfg": {"type": "number", "default": 1.0},
                "negative_prompt": {"type": "string", "default": ""},
                "seed": {"type": "integer", "default": -1},
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
        "description": "Check the status of a generation task (legacy — prefer get_image_status)",
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
# Public URL used in links returned to the browser — differs from COMFYUI_URL when the
# MCP container reaches ComfyUI via host.docker.internal but the browser uses localhost.
COMFYUI_PUBLIC_URL = os.getenv("COMFYUI_PUBLIC_URL", "http://localhost:8188")
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
    """Get a deep copy of the workflow for the selected model."""
    import copy

    selected = model or IMAGE_BACKEND
    if selected == "sdxl":
        return copy.deepcopy(SDXL_WORKFLOW)
    return copy.deepcopy(FLUX_WORKFLOW)


def _get_checkpoint(model: str | None = None) -> str:
    """Get the checkpoint filename for the selected model."""
    if os.getenv("FLUX_CKPT_FILE"):
        return os.getenv("FLUX_CKPT_FILE")
    selected = model or IMAGE_BACKEND
    return _MODEL_CKPT_MAP.get(selected, "flux1-schnell.safetensors")


def _build_image_workflow(
    prompt: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    negative_prompt: str,
    seed: int,
    model: str,
    checkpoint: str,
    lora: str,
    lora_strength: float,
) -> tuple[dict, int]:
    """Build the ComfyUI workflow dict. Returns (workflow, resolved_seed)."""
    import copy

    if seed == -1:
        seed = int(time.time() * 1000) % (2**32)

    workflow = _get_workflow(model)
    selected_model = model or IMAGE_BACKEND

    if selected_model == "sdxl":
        workflow["2"]["inputs"]["text"] = prompt
        workflow["3"]["inputs"]["text"] = negative_prompt
        workflow["4"]["inputs"]["width"] = width
        workflow["4"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["seed"] = seed
        workflow["5"]["inputs"]["steps"] = min(max(steps, 1), 50)
        workflow["5"]["inputs"]["cfg"] = min(max(cfg, 1), 20)
    else:
        # FLUX / flux-uncensored split-loader workflow
        workflow["4"]["inputs"]["text"] = prompt
        workflow["5"]["inputs"]["text"] = negative_prompt or ""
        workflow["6"]["inputs"]["width"] = width
        workflow["6"]["inputs"]["height"] = height
        workflow["8"]["inputs"]["seed"] = seed
        workflow["8"]["inputs"]["steps"] = min(max(steps, 1), 50)
        # FLUX: KSampler cfg must be 1.0 — guidance is controlled by FluxGuidance(7).
        # Passing cfg > 1.0 into KSampler applies broken CFG extrapolation on top of
        # flow-matching, producing noise. The `cfg` parameter routes to FluxGuidance.
        workflow["8"]["inputs"]["cfg"] = 1.0
        workflow["7"]["inputs"]["guidance"] = min(max(cfg, 0.0), 10.0)
        workflow["1"]["inputs"]["ckpt_name"] = _get_checkpoint(model)
        workflow["2"]["inputs"]["clip_name1"] = os.getenv(
            "FLUX_CLIP_L_FILE", "text_encoder/model.safetensors"
        )
        workflow["2"]["inputs"]["clip_name2"] = os.getenv(
            "FLUX_CLIP_T5_FILE", "text_encoder_2/model-00001-of-00002.safetensors"
        )
        workflow["3"]["inputs"]["vae_name"] = os.getenv("FLUX_VAE_FILE", "ae.safetensors")
        if checkpoint:
            workflow["1"]["inputs"]["ckpt_name"] = checkpoint

    if lora:
        wf = copy.deepcopy(workflow)
        if selected_model == "sdxl":
            wf["10"] = {
                "inputs": {
                    "model": ["1", 0],
                    "clip": ["1", 1],
                    "lora_name": lora,
                    "strength_model": lora_strength,
                    "strength_clip": lora_strength,
                },
                "class_type": "LoraLoader",
            }
            wf["5"]["inputs"]["model"] = ["10", 0]
            wf["2"]["inputs"]["clip"] = ["10", 1]
            wf["3"]["inputs"]["clip"] = ["10", 1]
        else:
            # FLUX: LoraLoader applies both model AND CLIP/T5 weights.
            # LoraLoaderModelOnly skips CLIP — most FLUX dev LoRAs include text encoder
            # weights; skipping them misaligns conditioning and produces noise/static.
            wf["11"] = {
                "inputs": {
                    "model": ["1", 0],
                    "clip": ["2", 0],
                    "lora_name": lora,
                    "strength_model": lora_strength,
                    "strength_clip": lora_strength,
                },
                "class_type": "LoraLoader",
            }
            wf["8"]["inputs"]["model"] = ["11", 0]
            wf["4"]["inputs"]["clip"] = ["11", 1]
            wf["5"]["inputs"]["clip"] = ["11", 1]
        workflow = wf

    return workflow, seed


def _eta_image(model: str, steps: int, width: int, height: int) -> int:
    """Estimate generation time in seconds for Apple Silicon MPS (no --force-fp16)."""
    scale = (width * height) / (1024 * 1024)
    if model == "sdxl":
        per_step = 10
    else:
        # FLUX (schnell and dev): ~26-28s/step at 1024x1024 on MPS without fp16
        per_step = 28
    return int(steps * per_step * max(scale, 0.25)) + 60


def _eta_human(seconds: int) -> str:
    if seconds < 90:
        return f"~{seconds}s"
    return f"~{round(seconds / 60)} min"


async def _submit_comfyui(workflow: dict) -> tuple[str | None, dict | None]:
    """Submit workflow to ComfyUI. Returns (prompt_id, None) or (None, error_dict)."""
    client_id = str(uuid.uuid4())
    client = await _get_client()
    try:
        resp = await client.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        resp.raise_for_status()
        return resp.json()["prompt_id"], None
    except httpx.ConnectError as e:
        return None, {
            "success": False,
            "error": (
                f"ComfyUI not available at {COMFYUI_URL}: {e}. "
                "Ensure ComfyUI is running and a model is installed."
            ),
        }
    except httpx.HTTPStatusError as e:
        try:
            error_detail = e.response.json().get("error", e.response.text[:200])
        except Exception:
            error_detail = e.response.text[:200] if e.response.text else str(e)
        return None, {
            "success": False,
            "error": f"ComfyUI rejected workflow (HTTP {e.response.status_code}): {error_detail}",
        }


@mcp.tool()
async def start_image_generation(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    cfg: float = 1.0,
    negative_prompt: str = "",
    seed: int = -1,
    model: str = "flux",
    checkpoint: str = "",
    lora: str = "",
    lora_strength: float = 1.0,
) -> dict:
    """
    Start image generation and return immediately with a job_id.

    Use this in Open WebUI / chat interfaces where the connection cannot stay open
    for 1-40 minutes. After calling this, tell the user the estimated wait time
    and use get_image_status(job_id) when they ask for the result.

    Args:
        prompt: Text description of the image
        model: 'flux' (schnell, fast ~1min), 'sdxl' (~8min), or 'flux-uncensored'
        steps: Diffusion steps — flux schnell default 4, flux dev 28, sdxl 35
        cfg: Guidance scale (FLUX: 1.0-5.0 maps to FluxGuidance; SDXL: 5.0-10.0)
        checkpoint: Override checkpoint filename (e.g. 'flux1-dev.safetensors')
        lora: LoRA filename to apply (optional)
        seed: -1 for random
    """
    workflow, seed = _build_image_workflow(
        prompt, width, height, steps, cfg, negative_prompt, seed, model, checkpoint, lora, lora_strength
    )
    prompt_id, err = await _submit_comfyui(workflow)
    if err:
        return err

    eta = _eta_image(model or IMAGE_BACKEND, steps, width, height)
    eta_str = _eta_human(eta)
    return {
        "success": True,
        "job_id": prompt_id,
        "eta_seconds": eta,
        "eta_human": eta_str,
        "seed": seed,
        "message": (
            f"Image generation started. Estimated time: {eta_str}. "
            f"Use get_image_status('{prompt_id}') to check progress and retrieve the result."
        ),
    }


@mcp.tool()
async def get_image_status(job_id: str) -> dict:
    """
    Check the status of an image generation job started with start_image_generation.

    Returns the image URL when complete, or current queue position if still running.

    Args:
        job_id: The job_id returned by start_image_generation
    """
    client = await _get_client()

    # Check history first (completed jobs)
    try:
        history_resp = await client.get(f"{COMFYUI_URL}/history/{job_id}")
        history = history_resp.json()
    except Exception as e:
        return {"status": "error", "job_id": job_id, "message": str(e)}

    if job_id in history:
        entry = history[job_id]
        status_str = entry.get("status", {}).get("status_str", "unknown")
        if status_str == "error":
            return {
                "status": "error",
                "job_id": job_id,
                "message": "Generation failed. Check ComfyUI logs.",
            }
        outputs = entry.get("outputs", {})
        for node_output in outputs.values():
            images = node_output.get("images", [])
            if images:
                filename = images[0]["filename"]
                url = f"{COMFYUI_PUBLIC_URL}/view?filename={filename}&type=output"
                return {
                    "status": "complete",
                    "job_id": job_id,
                    "url": url,
                    "filename": filename,
                    "message": f"Image ready. [View image]({url})",
                }
        return {
            "status": "complete",
            "job_id": job_id,
            "message": "Generation complete but no image output found — check ComfyUI logs.",
        }

    # Not in history — check live queue
    try:
        queue_resp = await client.get(f"{COMFYUI_URL}/queue")
        queue = queue_resp.json()
    except Exception:
        return {"status": "unknown", "job_id": job_id, "message": "Could not reach ComfyUI queue."}

    running = [e for e in queue.get("queue_running", []) if len(e) > 1 and e[1] == job_id]
    pending = queue.get("queue_pending", [])
    pending_ids = [e[1] for e in pending if len(e) > 1]

    if running:
        return {
            "status": "running",
            "job_id": job_id,
            "message": "Image is currently generating. Check back in a few minutes.",
        }
    if job_id in pending_ids:
        pos = pending_ids.index(job_id)
        return {
            "status": "queued",
            "job_id": job_id,
            "queue_position": pos,
            "message": f"Job is queued ({pos} job(s) ahead). Check back later.",
        }

    return {
        "status": "not_found",
        "job_id": job_id,
        "message": "Job not found in queue or history. It may have expired or never started.",
    }


@mcp.tool()
async def get_latest_images(count: int = 5) -> list[dict]:
    """
    Get the most recently generated images from ComfyUI.

    Useful for retrieving results without tracking job_ids, or for showing the user
    what has been generated in this session.

    Args:
        count: Number of recent images to return (default 5)
    """
    client = await _get_client()
    try:
        resp = await client.get(f"{COMFYUI_URL}/history")
        history = resp.json()
    except Exception as e:
        return [{"error": str(e)}]

    images: list[dict] = []
    for prompt_id, entry in history.items():
        if entry.get("status", {}).get("status_str") != "success":
            continue
        for node_output in entry.get("outputs", {}).values():
            for img in node_output.get("images", []):
                filename = img.get("filename", "")
                # Skip video files that appear as image frames
                if filename and not any(filename.endswith(ext) for ext in (".mp4", ".webm", ".gif")):
                    images.append({
                        "filename": filename,
                        "url": f"{COMFYUI_PUBLIC_URL}/view?filename={filename}&type=output",
                        "job_id": prompt_id,
                    })

    # Sort by filename — portal__XXXXX_.png sequential numbering gives recency order
    images.sort(key=lambda x: x["filename"], reverse=True)
    return images[:count]


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
    checkpoint: str = "",
    lora: str = "",
    lora_strength: float = 1.0,
) -> dict:
    """
    Generate an image using FLUX.1 or SDXL via ComfyUI. Blocks until complete.
    Returns a URL to the generated image file.

    WARNING: Takes 1-40 minutes depending on model and steps. For Open WebUI /
    chat use, prefer start_image_generation + get_image_status instead.

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
        checkpoint: Override checkpoint filename (optional)
        lora: LoRA filename to apply (optional, from models/loras/)
        lora_strength: LoRA strength 0.0-2.0 (default 1.0)
    """
    workflow, seed = _build_image_workflow(
        prompt, width, height, steps, cfg, negative_prompt, seed, model, checkpoint, lora, lora_strength
    )
    prompt_id, err = await _submit_comfyui(workflow)
    if err:
        return err

    client = await _get_client()
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
                    url = f"{COMFYUI_PUBLIC_URL}/view?filename={filename}&type=output"
                    return {
                        "success": True,
                        "filename": filename,
                        "url": url,
                        "prompt": prompt,
                        "seed": seed,
                        "message": f"Image generated successfully. [View image]({url})",
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
    """Check the status of an image generation job by its prompt_id (legacy alias for get_image_status)."""
    return await get_image_status(job_id)


if __name__ == "__main__":
    port = int(os.getenv("COMFYUI_MCP_PORT", "8910"))
    mcp.settings.port = port
    try:
        mcp.run(transport="streamable-http")
    finally:
        # Clean up shared httpx client on shutdown
        asyncio.run(_close_client())
