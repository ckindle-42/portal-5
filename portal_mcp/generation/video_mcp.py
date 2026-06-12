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

mcp = FastMCP("video-generation", host="0.0.0.0")

# Configurable timeout: VIDEO_TIMEOUT env var (seconds, default 3600 = 1 hr).
# 9 frames × 50 steps on Apple Silicon MPS ≈ 30-40 min; 1hr gives safe headroom.
VIDEO_TIMEOUT = int(os.environ.get("VIDEO_TIMEOUT", "3600"))

# Module-level httpx client — created once per process, reused for all requests.
# Eliminates TCP/TLS handshake overhead on every video generation call (P9).
_http_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=float(VIDEO_TIMEOUT), limits=httpx.Limits(max_connections=5)
        )
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
                "frames": {"type": "integer", "description": "Number of frames", "default": 9},
                "steps": {
                    "type": "integer",
                    "description": "Number of inference steps",
                    "default": 2,
                },
                "cfg": {"type": "number", "description": "CFG scale", "default": 6.0},
                "negative_prompt": {
                    "type": "string",
                    "description": "Negative prompt",
                    "default": "",
                },
                "seed": {"type": "integer", "description": "Random seed", "default": -1},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "start_video_generation",
        "description": (
            "Start video generation and return immediately with a job_id. "
            "Generation takes 30-90 min — use this instead of generate_video in OWUI. "
            "Follow up with get_video_status(job_id) to retrieve the result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "negative_prompt": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1280},
                "height": {"type": "integer", "default": 720},
                "frames": {"type": "integer", "default": 41},
                "steps": {"type": "integer", "default": 30},
                "cfg": {"type": "number", "default": 6.2},
                "shift": {"type": "number", "default": 9.8},
                "sampler": {"type": "string", "default": "uni_pc"},
                "seed": {"type": "integer", "default": -1},
                "image_url": {
                    "type": "string",
                    "description": "URL or local path to a start-frame image (required for wan22-ti2v-5b and wan22-s2v-14b)",
                    "default": "",
                },
                "audio_url": {
                    "type": "string",
                    "description": "URL or local path to an audio file (required for wan22-s2v-14b)",
                    "default": "",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "get_video_status",
        "description": "Check status of a video generation job. Returns URL when complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "get_latest_videos",
        "description": "Get the most recently generated videos from ComfyUI.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "default": 5},
            },
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
# Public URL used in links returned to the browser — differs from COMFYUI_URL when the
# MCP container reaches ComfyUI via host.docker.internal but the browser uses localhost.
COMFYUI_PUBLIC_URL = os.getenv("COMFYUI_PUBLIC_URL", "http://localhost:8188")
VIDEO_BACKEND = os.getenv(
    "VIDEO_BACKEND", "wan22"
)  # "wan22", "wan21-nsfw", "cogvideox", or "wan22-*"

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
#   hf download Comfy-Org/HunyuanVideo_repackaged \
#     --include "split_files/text_encoders/llava_llama3_fp8_scaled.safetensors" \
#     --local-dir ~/ComfyUI/models
VIDEO_MODEL_FILE = os.getenv(
    "VIDEO_MODEL_FILE",
    "Wan2.2-T2V-A14B/diffusion_pytorch_model_comfyui.safetensors",
)

# ── Wan2.1 NSFW backend (VIDEO_BACKEND=wan21-nsfw) ──────────────────────────
# Fully fine-tuned NSFW video model — equivalent of Flux_v8-NSFW for video.
# Architecture: Wan2.1-T2V-14B fine-tuned by NSFW-API (e15 = best quality).
# No LoRA needed — the checkpoint itself generates NSFW content.
#
# Required ComfyUI model files (all BF16, MPS-compatible):
#   models/diffusion_models/nsfw_wan_14b_e15.safetensors     (~28.6GB)
#   models/text_encoders/nsfw_wan_umt5-xxl_bf16_fixed.safetensors  (~10GB)
#   models/vae/wan_2.1_vae.safetensors                       (~242MB)
#
# Download:
#   hf download NSFW-API/NSFW_Wan_14b nsfw_wan_14b_e15.safetensors \
#       --local-dir ~/ComfyUI/models/diffusion_models/
#   hf download zootkitty/nsfw_wan_umt5-xxl_bf16_fixed nsfw_wan_umt5-xxl_bf16_fixed.safetensors \
#       --local-dir ~/ComfyUI/models/text_encoders/
#   hf download ratoenien/wan_2.1_vae wan_2.1_vae.safetensors \
#       --local-dir ~/ComfyUI/models/vae/
WAN21_NSFW_MODEL = os.getenv("WAN21_NSFW_MODEL", "nsfw_wan_14b_e15.safetensors")
WAN21_NSFW_CLIP = os.getenv("WAN21_NSFW_CLIP", "nsfw_wan_umt5-xxl_bf16_fixed.safetensors")
WAN21_NSFW_VAE = os.getenv("WAN21_NSFW_VAE", "wan_2.1_vae.safetensors")

# ── Wan 2.2 T2V-A14B model env vars ─────────────────────────────────────────
# After ./launch.sh pull-wan22, the HuggingFace repo downloads to
# ~/ComfyUI/models/diffusion_models/Wan2.2-T2V-A14B/ which includes
# diffusion_pytorch_model_comfyui.safetensors (ComfyUI merged format, ~24GB).
# UNETLoader resolves relative to models/diffusion_models/ — use the subdir path.
# Text encoder falls back to the NSFW umt5 (same architecture, works for SFW too).
# Override WAN22_T2V_CLIP to umt5_xxl_fp8_e4m3fn_scaled.safetensors for true
# Wan 2.2 standard model (requires separate download — not yet in pull-wan22).
WAN22_T2V_UNET = os.getenv(
    "WAN22_T2V_UNET",
    "Wan2.2-T2V-A14B/diffusion_pytorch_model_comfyui.safetensors",
)
WAN22_T2V_CLIP = os.getenv("WAN22_T2V_CLIP", "nsfw_wan_umt5-xxl_bf16_fixed.safetensors")
WAN22_T2V_VAE = os.getenv("WAN22_T2V_VAE", "wan_2.1_vae.safetensors")

# ── Wan 2.2 shared fp8 text encoder (TI2V-5B and S2V-14B) ────────────────────
# From Comfy-Org/Wan_2.1_ComfyUI_repackaged (same encoder, different packaging).
# Download: ./launch.sh pull-wan22
WAN22_CLIP_FP8 = os.getenv(
    "WAN22_CLIP_FP8", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
)

# ── Wan 2.2 TI2V-5B env vars ─────────────────────────────────────────────────
# Image-to-video: Wan22ImageToVideoLatent conditions on a start frame.
# Single-file ComfyUI format from Comfy-Org/Wan_2.2_ComfyUI_Repackaged.
# Download: ./launch.sh pull-wan22
WAN22_TI2V_MODEL = os.getenv(
    "WAN22_TI2V_MODEL", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"
)
WAN22_TI2V_VAE = os.getenv("WAN22_TI2V_VAE", "split_files/vae/wan2.2_vae.safetensors")

# ── Wan 2.2 S2V-14B env vars ─────────────────────────────────────────────────
# Sound-to-video: WanSoundImageToVideo conditions on audio + reference image.
# Requires audio_encoders/wav2vec2_large_english_fp16.safetensors.
# Download: ./launch.sh pull-wan22
WAN22_S2V_MODEL = os.getenv(
    "WAN22_S2V_MODEL", "split_files/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors"
)
WAN22_S2V_VAE = os.getenv("WAN22_S2V_VAE", "wan_2.1_vae.safetensors")
WAN22_S2V_AUDIO_ENCODER = os.getenv(
    "WAN22_S2V_AUDIO_ENCODER", "wav2vec2_large_english_fp16.safetensors"
)

# Hard caps to prevent LLM overrides from producing broken or multi-hour jobs.
# HunyuanVideo 720p model is designed for ≤1280×720; 832×480 is the reference resolution.
# Default VIDEO_MAX_STEPS=50 allows quality output; set to 2-4 in UAT environments
# where the 105s polling window requires fast generation.
VIDEO_MAX_FRAMES = int(os.getenv("VIDEO_MAX_FRAMES", "9"))
VIDEO_MAX_STEPS = int(os.getenv("VIDEO_MAX_STEPS", "50"))
VIDEO_MAX_WIDTH = int(os.getenv("VIDEO_MAX_WIDTH", "832"))
VIDEO_MAX_HEIGHT = int(os.getenv("VIDEO_MAX_HEIGHT", "480"))
# 9 frames at 8fps = 1.125s, which satisfies the UAT ≥1s requirement.
VIDEO_OUTPUT_FPS = int(os.getenv("VIDEO_OUTPUT_FPS", "8"))

# NSFW LoRA — applied when HUNYUAN_NSFW_LORA is set (non-empty).
# Default: nsfw-e7.safetensors (TheYuriLover/HunyuanVideo_nfsw_lora, trigger: "nsfwsks")
# Download: hf download TheYuriLover/HunyuanVideo_nfsw_lora nsfw-e7.safetensors \
#             --local-dir ~/ComfyUI/models/loras/
# Set HUNYUAN_NSFW_LORA="" to disable LoRA entirely.
HUNYUAN_NSFW_LORA = os.getenv("HUNYUAN_NSFW_LORA", "nsfw-e7.safetensors")
HUNYUAN_NSFW_LORA_STRENGTH = float(os.getenv("HUNYUAN_NSFW_LORA_STRENGTH", "0.85"))

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

# Wan2.1 NSFW T2V workflow — fully fine-tuned NSFW checkpoint, no LoRA required.
# Architecture mirrors the HunyuanVideo workflow but uses:
#   - CLIPLoader(type="wan") for umt5-xxl (single encoder, not dual)
#   - CFGGuider (positive + negative conditioning, real CFG scale)
#   - ModelSamplingSD3 shift=9.8 (recommended sweet spot for NSFW_Wan_14b)
#   - unipc sampler (recommended over euler for this fine-tune)
#   - wan_2.1_vae.safetensors instead of hunyuan VAE
#
# Node layout:
#   1: UNETLoader → model[0]
#   2: CLIPLoader(type="wan") → clip[0]
#   3: VAELoader → vae[0]
#   4: CLIPTextEncode(positive) → conditioning[0]
#   5: EmptyHunyuanLatentVideo → latent[0]
#   6: ModelSamplingSD3(shift=9.8) → model[0]
#   7: KSamplerSelect(unipc) → sampler[0]
#   8: BasicScheduler(steps) → sigmas[0]
#   9: RandomNoise(seed) → noise[0]
#  10: CFGGuider(model, positive, negative, cfg) → guider[0]
#  11: SamplerCustomAdvanced → latent[0]
#  12: VAEDecodeTiled → image[0]
#  13: CreateVideo → video[0]
#  14: SaveVideo
#  15: CLIPTextEncode(negative) → conditioning[0]
_WAN21_NSFW_T2V_WORKFLOW: dict = {
    "1": {
        "inputs": {"unet_name": WAN21_NSFW_MODEL, "weight_dtype": "default"},
        "class_type": "UNETLoader",
    },
    "2": {
        "inputs": {"clip_name": WAN21_NSFW_CLIP, "type": "wan"},
        "class_type": "CLIPLoader",
    },
    "3": {
        "inputs": {"vae_name": WAN21_NSFW_VAE},
        "class_type": "VAELoader",
    },
    "4": {
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
    "5": {
        "inputs": {"width": 1280, "height": 720, "length": 41, "batch_size": 1},
        "class_type": "EmptyHunyuanLatentVideo",
    },
    "6": {
        "inputs": {"model": ["1", 0], "shift": 9.8},
        "class_type": "ModelSamplingSD3",
    },
    "7": {
        "inputs": {"sampler_name": "uni_pc"},
        "class_type": "KSamplerSelect",
    },
    "8": {
        "inputs": {
            "model": ["6", 0],
            "scheduler": "simple",
            "steps": 30,
            "denoise": 1.0,
        },
        "class_type": "BasicScheduler",
    },
    "9": {
        "inputs": {"noise_seed": 1},
        "class_type": "RandomNoise",
    },
    "10": {
        "inputs": {
            "model": ["6", 0],
            "positive": ["4", 0],
            "negative": ["15", 0],
            "cfg": 6.2,
        },
        "class_type": "CFGGuider",
    },
    "11": {
        "inputs": {
            "noise": ["9", 0],
            "guider": ["10", 0],
            "sampler": ["7", 0],
            "sigmas": ["8", 0],
            "latent_image": ["5", 0],
        },
        "class_type": "SamplerCustomAdvanced",
    },
    "12": {
        "inputs": {
            "samples": ["11", 0],
            "vae": ["3", 0],
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
        "class_type": "VAEDecodeTiled",
    },
    "13": {
        "inputs": {"images": ["12", 0], "fps": 8.0},
        "class_type": "CreateVideo",
    },
    "14": {
        "inputs": {
            "video": ["13", 0],
            "filename_prefix": "portal_nsfw_",
            "format": "auto",
            "codec": "auto",
        },
        "class_type": "SaveVideo",
    },
    "15": {
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
}


# ── Wan 2.2 family (PHASE_PLAN_MODEL_REFRESH_V7_V2) ──────────────────────────
# T2V-A14B: real workflow, mirrors _WAN21_NSFW_T2V_WORKFLOW node layout so the
# same patching logic in _build_video_workflow() applies (nodes 4/5/6/7/8/9/10/13/15).
# Requires: ./launch.sh pull-wan22 (downloads Wan2.2-T2V-A14B/ to diffusion_models/).
# ComfyUI template reference: comfyui_workflow_templates_media_video/video_wan2_2_14B_t2v.json
#
# TI2V-5B: stub — requires Wan22ImageToVideoLatent (image input) which needs an
# image picker UI; planned once start_video_generation adds image_url parameter.
#
# Animate-14B / S2V-14B: stubs — new ComfyUI node types, require separate testing.
# ComfyUI templates: video_wan2_2_14B_animate.json, video_wan2_2_14B_s2v.json

# Wan 2.2 T2V-A14B — node layout mirrors NSFW T2V for re-use of patching logic.
# shift=8.0 is the Wan 2.2 default (vs 9.8 for NSFW fine-tune); CFGGuider same.
_WAN22_T2V_A14B_WORKFLOW: dict = {
    "1": {
        "inputs": {"unet_name": WAN22_T2V_UNET, "weight_dtype": "default"},
        "class_type": "UNETLoader",
    },
    "2": {
        "inputs": {"clip_name": WAN22_T2V_CLIP, "type": "wan"},
        "class_type": "CLIPLoader",
    },
    "3": {
        "inputs": {"vae_name": WAN22_T2V_VAE},
        "class_type": "VAELoader",
    },
    "4": {
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
    "5": {
        "inputs": {"width": 1280, "height": 720, "length": 41, "batch_size": 1},
        "class_type": "EmptyHunyuanLatentVideo",
    },
    "6": {
        "inputs": {"model": ["1", 0], "shift": 8.0},
        "class_type": "ModelSamplingSD3",
    },
    "7": {
        "inputs": {"sampler_name": "uni_pc"},
        "class_type": "KSamplerSelect",
    },
    "8": {
        "inputs": {
            "model": ["6", 0],
            "scheduler": "simple",
            "steps": 30,
            "denoise": 1.0,
        },
        "class_type": "BasicScheduler",
    },
    "9": {
        "inputs": {"noise_seed": 1},
        "class_type": "RandomNoise",
    },
    "10": {
        "inputs": {
            "model": ["6", 0],
            "positive": ["4", 0],
            "negative": ["15", 0],
            "cfg": 6.0,
        },
        "class_type": "CFGGuider",
    },
    "11": {
        "inputs": {
            "noise": ["9", 0],
            "guider": ["10", 0],
            "sampler": ["7", 0],
            "sigmas": ["8", 0],
            "latent_image": ["5", 0],
        },
        "class_type": "SamplerCustomAdvanced",
    },
    "12": {
        "inputs": {
            "samples": ["11", 0],
            "vae": ["3", 0],
            "tile_size": 256,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 8,
        },
        "class_type": "VAEDecodeTiled",
    },
    "13": {
        "inputs": {"images": ["12", 0], "fps": 8.0},
        "class_type": "CreateVideo",
    },
    "14": {
        "inputs": {
            "video": ["13", 0],
            "filename_prefix": "portal_wan22_t2v_",
            "format": "auto",
            "codec": "auto",
        },
        "class_type": "SaveVideo",
    },
    "15": {
        "inputs": {"text": "", "clip": ["2", 0]},
        "class_type": "CLIPTextEncode",
    },
}

# Wan 2.2 TI2V-5B — image-to-video using Wan22ImageToVideoLatent.
# Node layout matches video_wan2_2_5B_ti2v.json template (node IDs preserved).
# image_url → /upload/image → LoadImage[56] → Wan22ImageToVideoLatent[55] → KSampler[3].
# Default: 1280×704, 121 frames (≈5s at 24fps). Requires pull-wan22.
_WAN22_TI2V_5B_WORKFLOW: dict = {
    "37": {
        "inputs": {"unet_name": WAN22_TI2V_MODEL, "weight_dtype": "default"},
        "class_type": "UNETLoader",
    },
    "38": {
        "inputs": {"clip_name": WAN22_CLIP_FP8, "type": "wan"},
        "class_type": "CLIPLoader",
    },
    "39": {
        "inputs": {"vae_name": WAN22_TI2V_VAE},
        "class_type": "VAELoader",
    },
    "48": {
        "inputs": {"model": ["37", 0], "shift": 8.0},
        "class_type": "ModelSamplingSD3",
    },
    "56": {
        "inputs": {"image": "example.png", "upload": "image"},
        "class_type": "LoadImage",
    },
    "55": {
        "inputs": {
            "vae": ["39", 0],
            "start_image": ["56", 0],
            "width": 1280,
            "height": 704,
            "length": 121,
            "batch_size": 1,
        },
        "class_type": "Wan22ImageToVideoLatent",
    },
    "6": {"inputs": {"text": "", "clip": ["38", 0]}, "class_type": "CLIPTextEncode"},
    "7": {"inputs": {"text": "", "clip": ["38", 0]}, "class_type": "CLIPTextEncode"},
    "3": {
        "inputs": {
            "model": ["48", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["55", 0],
            "seed": 1,
            "control_after_generate": "randomize",
            "steps": 20,
            "cfg": 5.0,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
        },
        "class_type": "KSampler",
    },
    "8": {
        "inputs": {"samples": ["3", 0], "vae": ["39", 0]},
        "class_type": "VAEDecode",
    },
    "57": {
        "inputs": {"images": ["8", 0], "fps": 24},
        "class_type": "CreateVideo",
    },
    "58": {
        "inputs": {
            "video": ["57", 0],
            "filename_prefix": "portal_ti2v_",
            "format": "auto",
            "codec": "auto",
        },
        "class_type": "SaveVideo",
    },
}

_WAN22_ANIMATE_14B_WORKFLOW: dict = {
    "_stub": True,
    "_stub_message": (
        "Wan 2.2 Animate-14B requires SAM2 segmentation, DWPreprocessor, and CLIPVision "
        "custom ComfyUI nodes plus a community KJ-format model "
        "(Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors). "
        "Too many non-standard dependencies to wire automatically. "
        "Use the ComfyUI template: video_wan2_2_14B_animate.json (installed in ComfyUI venv)."
    ),
}

# Wan 2.2 S2V-14B — sound-to-video using WanSoundImageToVideo.
# Requires: audio_url (reference audio) + image_url (reference frame).
# WanSoundImageToVideo outputs (positive, negative, latent) — KSampler uses all 3.
# Default: 640×640, 77 frames (≈4.8s at 16fps). Requires pull-wan22.
_WAN22_S2V_14B_WORKFLOW: dict = {
    "1": {
        "inputs": {"unet_name": WAN22_S2V_MODEL, "weight_dtype": "default"},
        "class_type": "UNETLoader",
    },
    "2": {
        "inputs": {"clip_name": WAN22_CLIP_FP8, "type": "wan"},
        "class_type": "CLIPLoader",
    },
    "3": {
        "inputs": {"vae_name": WAN22_S2V_VAE},
        "class_type": "VAELoader",
    },
    "4": {
        "inputs": {"audio_encoder_name": WAN22_S2V_AUDIO_ENCODER},
        "class_type": "AudioEncoderLoader",
    },
    "5": {
        "inputs": {"audio": "", "start_time": None, "duration": None},
        "class_type": "LoadAudio",
    },
    "6": {
        "inputs": {"image": "", "upload": "image"},
        "class_type": "LoadImage",
    },
    "7": {
        "inputs": {"audio_encoder": ["4", 0], "audio": ["5", 0]},
        "class_type": "AudioEncoderEncode",
    },
    "8": {"inputs": {"text": "", "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
    "9": {"inputs": {"text": "", "clip": ["2", 0]}, "class_type": "CLIPTextEncode"},
    "10": {
        "inputs": {"model": ["1", 0], "shift": 8.0},
        "class_type": "ModelSamplingSD3",
    },
    "11": {
        "inputs": {
            "positive": ["8", 0],
            "negative": ["9", 0],
            "vae": ["3", 0],
            "audio_encoder_output": ["7", 0],
            "ref_image": ["6", 0],
            "width": 640,
            "height": 640,
            "length": 77,
            "batch_size": 1,
        },
        "class_type": "WanSoundImageToVideo",
    },
    "12": {
        "inputs": {
            "model": ["10", 0],
            "positive": ["11", 0],
            "negative": ["11", 1],
            "latent_image": ["11", 2],
            "seed": 1,
            "control_after_generate": "randomize",
            "steps": 20,
            "cfg": 6.0,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "denoise": 1.0,
        },
        "class_type": "KSampler",
    },
    "13": {
        "inputs": {"samples": ["12", 0], "vae": ["3", 0]},
        "class_type": "VAEDecode",
    },
    "14": {
        "inputs": {"images": ["13", 0], "fps": 16},
        "class_type": "CreateVideo",
    },
    "15": {
        "inputs": {
            "video": ["14", 0],
            "filename_prefix": "portal_s2v_",
            "format": "auto",
            "codec": "auto",
        },
        "class_type": "SaveVideo",
    },
}

# Public map — used for routing and verification
WAN22_WORKFLOWS: dict[str, dict] = {
    "wan22-t2v-a14b": _WAN22_T2V_A14B_WORKFLOW,
    "wan22-ti2v-5b": _WAN22_TI2V_5B_WORKFLOW,
    "wan22-animate-14b": _WAN22_ANIMATE_14B_WORKFLOW,
    "wan22-s2v-14b": _WAN22_S2V_14B_WORKFLOW,
}


def _get_workflow(model: str = "") -> dict:
    """Get a deep copy of the workflow based on model override or VIDEO_BACKEND env var."""
    import copy

    # Explicit Wan 2.2 model selection overrides VIDEO_BACKEND
    if model in WAN22_WORKFLOWS:
        wf = WAN22_WORKFLOWS[model]
        if wf.get("_stub"):
            raise RuntimeError(wf["_stub_message"])
        return copy.deepcopy(wf)

    if VIDEO_BACKEND == "cogvideox":
        return copy.deepcopy(_COGVIDEOX_WORKFLOW)

    if VIDEO_BACKEND == "wan21-nsfw":
        return copy.deepcopy(_WAN21_NSFW_T2V_WORKFLOW)

    # Default: HunyuanVideo ("wan22") with optional NSFW LoRA
    wf = copy.deepcopy(_WAN22_T2V_WORKFLOW)
    if HUNYUAN_NSFW_LORA:
        wf["16"] = {
            "inputs": {
                "model": ["1", 0],
                "lora_name": HUNYUAN_NSFW_LORA,
                "strength_model": HUNYUAN_NSFW_LORA_STRENGTH,
            },
            "class_type": "LoraLoaderModelOnly",
        }
        wf["6"]["inputs"]["model"] = ["16", 0]
    return wf


@mcp.tool()
async def generate_video(
    prompt: str,
    width: int = 832,
    height: int = 480,
    frames: int = 9,
    fps: int = VIDEO_OUTPUT_FPS,
    steps: int = 2,
    cfg: float = 6.0,
    negative_prompt: str = "",
    model: str = "",
    seed: int = -1,
) -> dict:
    """
    Generate a video and block until complete. WARNING: takes 30-60 minutes.
    For Open WebUI / chat use, prefer start_video_generation + get_video_status instead.

    Args:
        prompt: Text description of the video to generate
        width: Video width in pixels (default 832)
        height: Video height in pixels (default 480)
        frames: Number of frames (default 9, ≈1.1s at 8fps). Max VIDEO_MAX_FRAMES.
        fps: Output fps (default VIDEO_OUTPUT_FPS=8; not exposed in manifest)
        steps: Diffusion inference steps (default 2)
        cfg: CFG scale (default 6.0)
        negative_prompt: Things to avoid in the video
        model: Override model name (optional, auto-detected from backend)
        seed: Random seed, -1 for random
    """
    workflow, seed = _build_video_workflow(
        prompt, width, height, frames, fps, steps, cfg, model, seed, negative_prompt=negative_prompt
    )
    prompt_id, err = await _submit_comfyui(workflow)
    if err:
        logger.error("ComfyUI /prompt error: %s", err)
        return err

    client = await _get_client()
    poll_interval = 2
    max_polls = VIDEO_TIMEOUT // poll_interval
    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)
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
                                f"ComfyUI error in {err.get('node_type', '?')} "
                                f"(node {err.get('node_id', '?')}): "
                                f"{err.get('exception_message', 'unknown error')}"
                            ),
                        }
                return {"success": False, "error": "ComfyUI workflow failed (unknown error)"}

            outputs = entry.get("outputs", {})
            for node_output in outputs.values():
                # SaveVideo → "images" key with animated=True (ComfyUI ≥0.16)
                # VHS_VideoCombine → "gifs" key
                # Legacy SaveVideo → "videos" key
                images = node_output.get("images", [])
                animated = node_output.get("animated", [])
                video_files = (
                    node_output.get("videos")
                    or node_output.get("gifs")
                    # animated images from SaveVideo (ComfyUI native node)
                    or (images if any(animated) else [])
                    or []
                )
                if video_files and isinstance(video_files, list) and len(video_files) > 0:
                    filename = (
                        video_files[0].get("filename")
                        if isinstance(video_files[0], dict)
                        else str(video_files[0])
                    )
                    if filename:
                        url = f"{COMFYUI_PUBLIC_URL}/view?filename={filename}&type=output"
                        return {
                            "success": True,
                            "filename": filename,
                            "url": url,
                            "prompt": prompt,
                            "seed": seed,
                            "frames": frames,
                            "fps": fps,
                            "message": f"Video generated successfully. [Download video]({url})",
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

    return {
        "success": False,
        "error": f"Video generation timed out after {VIDEO_TIMEOUT // 60} minutes",
    }


def _eta_video(frames: int, steps: int) -> int:
    """Estimate video generation time in seconds for Apple Silicon MPS."""
    # HunyuanVideo processes all frames as a 3D attention tensor per step.
    # Observed: 9 frames × 50 steps ≈ 2400s on M-series. ~48s/step + 120s overhead.
    per_step = 50
    return int(steps * per_step) + 120


def _eta_human(seconds: int) -> str:
    if seconds < 90:
        return f"~{seconds}s"
    return f"~{round(seconds / 60)} min"


def _extract_video_url(outputs: dict) -> str | None:
    """Extract the first video filename from ComfyUI output dict, return public URL or None."""
    for node_output in outputs.values():
        images = node_output.get("images", [])
        animated = node_output.get("animated", [])
        video_files = (
            node_output.get("videos")
            or node_output.get("gifs")
            or (images if any(animated) else [])
            or []
        )
        if video_files and isinstance(video_files, list):
            filename = (
                video_files[0].get("filename")
                if isinstance(video_files[0], dict)
                else str(video_files[0])
            )
            if filename:
                return f"{COMFYUI_PUBLIC_URL}/view?filename={filename}&type=output"
    return None


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
            "error": f"ComfyUI not available at {COMFYUI_URL}: {e}. Ensure ComfyUI is running.",
        }
    except httpx.HTTPStatusError as e:
        raw_body = e.response.text[:500]
        try:
            error_detail = e.response.json().get("error", raw_body)
        except Exception:
            error_detail = raw_body
        return None, {
            "success": False,
            "error": f"ComfyUI rejected workflow (HTTP {e.response.status_code}): {error_detail}",
        }


async def _upload_image_to_comfyui(image_url: str) -> str:
    """Fetch image from URL or local path, upload to ComfyUI, return filename."""
    import mimetypes

    client = await _get_client()
    if image_url.startswith(("http://", "https://")):
        resp = await client.get(image_url)
        resp.raise_for_status()
        data = resp.content
        fname = image_url.split("/")[-1].split("?")[0] or "upload.png"
    else:
        with open(image_url, "rb") as fh:
            data = fh.read()
        fname = os.path.basename(image_url)
    content_type = mimetypes.guess_type(fname)[0] or "image/png"
    upload_resp = await client.post(
        f"{COMFYUI_URL}/upload/image",
        files={"image": (fname, data, content_type)},
        data={"type": "input", "overwrite": "true"},
    )
    upload_resp.raise_for_status()
    return upload_resp.json()["name"]


async def _upload_audio_to_comfyui(audio_url: str) -> str:
    """Fetch audio from URL or local path, make available to ComfyUI, return filename."""
    import mimetypes

    client = await _get_client()
    if audio_url.startswith(("http://", "https://")):
        resp = await client.get(audio_url)
        resp.raise_for_status()
        data = resp.content
        fname = audio_url.split("/")[-1].split("?")[0] or "upload.mp3"
    else:
        with open(audio_url, "rb") as fh:
            data = fh.read()
        fname = os.path.basename(audio_url)
    content_type = mimetypes.guess_type(fname)[0] or "audio/mpeg"

    # Try /upload/audio (ComfyUI 0.3.x+)
    try:
        upload_resp = await client.post(
            f"{COMFYUI_URL}/upload/audio",
            files={"audio": (fname, data, content_type)},
            data={"type": "input", "overwrite": "true"},
        )
        upload_resp.raise_for_status()
        return upload_resp.json()["name"]
    except Exception:
        pass

    # Fallback: write directly to ComfyUI input directory
    comfyui_input = os.path.expanduser(os.getenv("COMFYUI_INPUT_DIR", "~/ComfyUI/input"))
    os.makedirs(comfyui_input, exist_ok=True)
    with open(os.path.join(comfyui_input, fname), "wb") as fh:
        fh.write(data)
    return fname


def _build_video_workflow(
    prompt: str,
    width: int,
    height: int,
    frames: int,
    fps: int,
    steps: int,
    cfg: float,
    model: str,
    seed: int,
    shift: float = 9.8,
    sampler: str = "uni_pc",
    negative_prompt: str = "",
    image_filename: str = "",
    audio_filename: str = "",
) -> tuple[dict, int]:
    """Build video workflow dict. Returns (workflow, resolved_seed)."""
    if seed == -1:
        seed = int(time.time() * 1000) % (2**32)

    # TI2V and S2V have larger native resolutions / frame counts — bypass standard caps.
    if model not in ("wan22-ti2v-5b", "wan22-s2v-14b"):
        frames = min(frames, VIDEO_MAX_FRAMES)
        width = min(width, VIDEO_MAX_WIDTH)
        height = min(height, VIDEO_MAX_HEIGHT)
    steps = min(steps, VIDEO_MAX_STEPS)
    fps = min(fps, VIDEO_OUTPUT_FPS)

    workflow = _get_workflow(model)

    if model == "wan22-t2v-a14b":
        # Same node layout as wan21-nsfw (nodes 4/5/6/7/8/9/10/13/15)
        workflow["4"]["inputs"]["text"] = prompt
        workflow["15"]["inputs"]["text"] = negative_prompt
        workflow["5"]["inputs"]["width"] = width
        workflow["5"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["length"] = frames
        workflow["6"]["inputs"]["shift"] = shift
        workflow["7"]["inputs"]["sampler_name"] = sampler
        workflow["8"]["inputs"]["steps"] = steps
        workflow["9"]["inputs"]["noise_seed"] = seed
        workflow["10"]["inputs"]["cfg"] = cfg
        workflow["13"]["inputs"]["fps"] = float(fps)
        return workflow, seed

    if model == "wan22-ti2v-5b":
        if not image_filename:
            raise ValueError("wan22-ti2v-5b requires image_url — provide a start-frame image")
        workflow["56"]["inputs"]["image"] = image_filename
        workflow["6"]["inputs"]["text"] = prompt
        workflow["7"]["inputs"]["text"] = negative_prompt
        workflow["55"]["inputs"]["width"] = width
        workflow["55"]["inputs"]["height"] = height
        workflow["55"]["inputs"]["length"] = frames
        workflow["3"]["inputs"]["steps"] = steps
        workflow["3"]["inputs"]["cfg"] = cfg
        workflow["3"]["inputs"]["seed"] = seed
        workflow["3"]["inputs"]["sampler_name"] = sampler
        workflow["57"]["inputs"]["fps"] = float(fps)
        return workflow, seed

    if model == "wan22-s2v-14b":
        if not audio_filename:
            raise ValueError("wan22-s2v-14b requires audio_url — provide a reference audio file")
        if not image_filename:
            raise ValueError("wan22-s2v-14b requires image_url — provide a reference image frame")
        workflow["5"]["inputs"]["audio"] = audio_filename
        workflow["6"]["inputs"]["image"] = image_filename
        workflow["8"]["inputs"]["text"] = prompt
        workflow["9"]["inputs"]["text"] = negative_prompt
        workflow["11"]["inputs"]["width"] = width
        workflow["11"]["inputs"]["height"] = height
        workflow["11"]["inputs"]["length"] = frames
        workflow["12"]["inputs"]["steps"] = steps
        workflow["12"]["inputs"]["cfg"] = cfg
        workflow["12"]["inputs"]["seed"] = seed
        workflow["12"]["inputs"]["sampler_name"] = sampler
        workflow["14"]["inputs"]["fps"] = float(fps)
        return workflow, seed

    if VIDEO_BACKEND == "cogvideox":
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
    elif VIDEO_BACKEND == "wan21-nsfw":
        # Wan2.1 NSFW: CLIPLoader(2), CFGGuider(10), negative(15), CreateVideo(13)
        if model and model.endswith(".safetensors"):
            workflow["1"]["inputs"]["unet_name"] = model
        workflow["4"]["inputs"]["text"] = prompt
        workflow["15"]["inputs"]["text"] = negative_prompt
        workflow["5"]["inputs"]["width"] = width
        workflow["5"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["length"] = frames
        workflow["6"]["inputs"]["shift"] = shift
        workflow["7"]["inputs"]["sampler_name"] = sampler
        workflow["8"]["inputs"]["steps"] = steps
        workflow["9"]["inputs"]["noise_seed"] = seed
        workflow["10"]["inputs"]["cfg"] = cfg
        workflow["13"]["inputs"]["fps"] = float(fps)
    else:
        # HunyuanVideo ("wan22"): DualCLIPLoader(2), FluxGuidance(10), CreateVideo(14)
        if model and model.endswith(".safetensors"):
            workflow["1"]["inputs"]["unet_name"] = model
        workflow["4"]["inputs"]["text"] = prompt
        workflow["5"]["inputs"]["width"] = width
        workflow["5"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["length"] = frames
        workflow["8"]["inputs"]["steps"] = steps
        workflow["9"]["inputs"]["noise_seed"] = seed
        workflow["10"]["inputs"]["guidance"] = cfg
        workflow["14"]["inputs"]["fps"] = float(fps)

    return workflow, seed


@mcp.tool()
async def start_video_generation(
    prompt: str,
    width: int = 1280,
    height: int = 720,
    frames: int = 41,
    steps: int = 30,
    cfg: float = 6.2,
    negative_prompt: str = "",
    model: str = "",
    seed: int = -1,
    shift: float = 9.8,
    sampler: str = "uni_pc",
    image_url: str = "",
    audio_url: str = "",
) -> dict:
    """
    Start video generation and return immediately with a job_id.

    Use this in Open WebUI / chat interfaces — generation takes 30-90 minutes.
    After calling this, tell the user the estimated wait time and use
    get_video_status(job_id) when they ask for the result.

    Args:
        prompt: Text description of the video.
        width: Width in pixels (default 1280 for 720p)
        height: Height in pixels (default 720 for 720p)
        frames: Number of frames (default 41 ≈ 5s at 8fps)
        steps: Diffusion steps (default 30; 25 for faster preview, 35 for quality)
        cfg: Guidance scale (default 6.2; range 5.5–7.0)
        negative_prompt: Things to avoid in the video
        shift: ModelSamplingSD3 shift (default 9.8; range 8–11, higher = more motion)
        sampler: Sampler name (default unipc; dpm++_2m also works well)
        seed: -1 for random
        image_url: URL or local path to a start-frame image (required for wan22-ti2v-5b and wan22-s2v-14b)
        audio_url: URL or local path to an audio file (required for wan22-s2v-14b)
    """
    fps = VIDEO_OUTPUT_FPS

    # Upload media files before building workflow
    image_filename = ""
    audio_filename = ""
    if image_url:
        try:
            image_filename = await _upload_image_to_comfyui(image_url)
        except Exception as e:
            return {"success": False, "error": f"Image upload failed: {e}"}
    if audio_url:
        try:
            audio_filename = await _upload_audio_to_comfyui(audio_url)
        except Exception as e:
            return {"success": False, "error": f"Audio upload failed: {e}"}

    try:
        workflow, seed = _build_video_workflow(
            prompt,
            width,
            height,
            frames,
            fps,
            steps,
            cfg,
            model,
            seed,
            shift,
            sampler,
            negative_prompt,
            image_filename,
            audio_filename,
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}
    prompt_id, err = await _submit_comfyui(workflow)
    if err:
        return err

    # TI2V/S2V bypass the standard frame cap — use their actual frame count for ETA
    if model in ("wan22-ti2v-5b", "wan22-s2v-14b"):
        actual_frames = frames
    else:
        actual_frames = min(frames, VIDEO_MAX_FRAMES)
    actual_steps = min(steps, VIDEO_MAX_STEPS)
    eta = _eta_video(actual_frames, actual_steps)
    eta_str = _eta_human(eta)
    return {
        "success": True,
        "job_id": prompt_id,
        "eta_seconds": eta,
        "eta_human": eta_str,
        "seed": seed,
        "frames": actual_frames,
        "fps": fps,
        "message": (
            f"Video generation started ({actual_frames} frames, {actual_steps} steps). "
            f"Estimated time: {eta_str}. "
            f"Use get_video_status('{prompt_id}') to check progress and retrieve the result."
        ),
    }


@mcp.tool()
async def get_video_status(job_id: str) -> dict:
    """
    Check the status of a video generation job started with start_video_generation.

    Returns the video URL when complete, or current queue position if still running.

    Args:
        job_id: The job_id returned by start_video_generation
    """
    client = await _get_client()

    try:
        history_resp = await client.get(f"{COMFYUI_URL}/history/{job_id}")
        history = history_resp.json()
    except Exception as e:
        return {"status": "error", "job_id": job_id, "message": str(e)}

    if job_id in history:
        entry = history[job_id]
        status_str = entry.get("status", {}).get("status_str", "unknown")

        if status_str == "error":
            msgs = entry.get("status", {}).get("messages", [])
            for msg in reversed(msgs):
                if isinstance(msg, list) and msg[0] == "execution_error":
                    err = msg[1] if len(msg) > 1 else {}
                    return {
                        "status": "error",
                        "job_id": job_id,
                        "message": (
                            f"ComfyUI error in {err.get('node_type', '?')}: "
                            f"{err.get('exception_message', 'unknown error')}"
                        ),
                    }
            return {"status": "error", "job_id": job_id, "message": "Generation failed."}

        url = _extract_video_url(entry.get("outputs", {}))
        if url:
            return {
                "status": "complete",
                "job_id": job_id,
                "url": url,
                "message": f"Video ready. [Download video]({url})",
            }
        return {
            "status": "complete",
            "job_id": job_id,
            "message": "Generation complete but no video output found — check ComfyUI logs.",
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
            "message": "Video is currently generating. HunyuanVideo takes 30-60 min — check back later.",
        }
    if job_id in pending_ids:
        pos = pending_ids.index(job_id)
        return {
            "status": "queued",
            "job_id": job_id,
            "queue_position": pos,
            "message": f"Job is queued ({pos} job(s) ahead).",
        }

    return {
        "status": "not_found",
        "job_id": job_id,
        "message": "Job not found in queue or history. It may have expired or never started.",
    }


@mcp.tool()
async def get_latest_videos(count: int = 5) -> list[dict]:
    """
    Get the most recently generated videos from ComfyUI.

    Args:
        count: Number of recent videos to return (default 5)
    """
    client = await _get_client()
    try:
        resp = await client.get(f"{COMFYUI_URL}/history")
        history = resp.json()
    except Exception as e:
        return [{"error": str(e)}]

    videos: list[dict] = []
    for prompt_id, entry in history.items():
        if entry.get("status", {}).get("status_str") != "success":
            continue
        url = _extract_video_url(entry.get("outputs", {}))
        if url:
            filename = url.split("filename=")[-1].split("&")[0]
            videos.append(
                {
                    "filename": filename,
                    "url": url,
                    "job_id": prompt_id,
                }
            )

    videos.sort(key=lambda x: x["filename"], reverse=True)
    return videos[:count]


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


@mcp.custom_route("/tools/{tool_name}", methods=["POST"])
async def invoke_tool(request):
    """REST dispatch endpoint used by portal-pipeline tool_registry."""
    tool_name = request.path_params["tool_name"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    arguments = body.get("arguments", {})

    try:
        import inspect

        logger.info("invoke_tool: %s args=%s", tool_name, arguments)
        dispatch = {
            "generate_video": generate_video,
            "start_video_generation": start_video_generation,
            "get_video_status": get_video_status,
            "get_latest_videos": get_latest_videos,
            "list_video_models": list_video_models,
        }
        if tool_name not in dispatch:
            return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)
        fn = dispatch[tool_name]
        valid = set(inspect.signature(fn).parameters.keys())
        filtered = {k: v for k, v in arguments.items() if k in valid}
        result = await fn(**filtered)
        if tool_name == "list_video_models":
            return JSONResponse({"models": result})
        return JSONResponse(result if isinstance(result, dict) else {"result": result})
    except Exception as e:
        logger.exception("Tool invocation failed for %s", tool_name)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


if __name__ == "__main__":
    port = int(os.getenv("VIDEO_MCP_PORT", "8911"))
    mcp.settings.port = port
    try:
        mcp.run(transport="streamable-http")
    finally:
        asyncio.run(_close_client())
