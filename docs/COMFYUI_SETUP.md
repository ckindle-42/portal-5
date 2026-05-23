# Portal 6.0.0 — ComfyUI Setup Guide

ComfyUI handles image and video generation. It runs natively on the host
for Metal GPU access on Apple Silicon.

## Quick Install (Apple Silicon)

```bash
./launch.sh install-comfyui
```

This clones ComfyUI to `~/ComfyUI`, installs PyTorch with MPS support,
and registers it as a launchd service that auto-starts on login.

## Download Models

```bash
# Default: flux-schnell (image) + wan2.2 (video)
./launch.sh download-comfyui-models

# Choose a different image model:
IMAGE_MODEL=juggernaut-xl ./launch.sh download-comfyui-models

# All image model options:
#   flux-schnell (~12GB, default)    flux-dev (~24GB, needs HF_TOKEN)
#   flux-uncensored (~24GB)          flux2-klein (~20GB)
#   sdxl (~7GB)                      juggernaut-xl (~7GB, photoreal NSFW)
#   realvis-xl (~7GB, photoreal)     animagine-xl (~7GB, anime)
#   sdxl-turbo (~7GB, fast 1-4 step)

# All video model options:
#   wan2.2 (~18GB, default)          wan2.2-uncensored (~20GB)
#   skyreels-v1 (~15GB)              mochi-1 (~15GB)
#   stable-video-diffusion (~10GB)

# NSFW video (wan21-nsfw backend) — download separately, not via launch.sh:
hf download NSFW-API/NSFW_Wan_14b nsfw_wan_14b_e15.safetensors \
    --local-dir ~/ComfyUI/models/diffusion_models/
hf download zootkitty/nsfw_wan_umt5-xxl_bf16_fixed nsfw_wan_umt5-xxl_bf16_fixed.safetensors \
    --local-dir ~/ComfyUI/models/text_encoders/
hf download ratoenien/wan_2.1_vae wan_2.1_vae.safetensors \
    --local-dir ~/ComfyUI/models/vae/
# Then set VIDEO_BACKEND=wan21-nsfw in .env and restart: docker compose restart mcp-video
```

## Wan 2.2 Family (v6.2 addition)

Wan 2.2 is the MoE successor to Wan 2.1 (27B total / 14B active per step). Four variants are supported as parallel ComfyUI workflows. The Wan 2.1 NSFW pipeline is unchanged and remains the default for NSFW-tagged requests.

| Variant | Model ID | Size | Best for |
|---|---|---|---|
| `wan22-t2v-a14b` | `wan22-t2v-a14b` | 27B/14B-active | Cinematic-quality text-to-video |
| `wan22-ti2v-5b` | `wan22-ti2v-5b` | 5B | Fast single-GPU text/image-to-video (~9 min per 5s clip) |
| `wan22-animate-14b` | `wan22-animate-14b` | 14B | Character animation / replacement (**NEW capability**) |
| `wan22-s2v-14b` | `wan22-s2v-14b` | 14B | Speech-driven video generation (**NEW capability**) |

All four are Apache 2.0 licensed.

### Step 1 — Pull the weights (opt-in, ~80GB total)

```bash
# Pull all four Wan 2.2 variants
./launch.sh pull-wan22

# Or selectively (e.g., only the fast 5B variant first)
huggingface-cli download Wan-AI/Wan2.2-TI2V-5B \
    --local-dir ~/ComfyUI/models/diffusion_models/Wan2.2-TI2V-5B
```

### Step 2 — Export ComfyUI workflow templates

The Wan 2.2 workflow dicts in `portal_mcp/generation/video_mcp.py` are stubs until exported. For each variant:

1. Open ComfyUI → Workflow → Browse Templates → Video
2. Load the template ("Wan2.2 14B T2V", "Wan2.2 5B TI2V", "Wan2.2-Animate-14B", "Wan2.2-S2V-14B")
3. Verify the model loads and runs a test prompt
4. Export as JSON and use the node graph to populate the corresponding `_WAN22_*_WORKFLOW` dict in `portal_mcp/generation/video_mcp.py`

Until step 2 is completed, calling a `wan22-*` model preset will raise a `RuntimeError` with instructions.

### Step 3 — Use

```bash
# Fast preset (TI2V-5B, ~9 min per 5s clip)
python3 scripts/gen-video.py "a woman dancing in a sunlit garden" --preset wan22-fast

# Cinematic quality (T2V-A14B, slower)
python3 scripts/gen-video.py "a sweeping aerial view of mountain peaks at sunset" --preset wan22-quality

# Explicit model override
python3 scripts/gen-video.py "your prompt" --model wan22-t2v-a14b --steps 40

# Via MCP tool
curl -X POST http://localhost:8911/tools/start_video_generation \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"prompt": "your prompt", "model": "wan22-ti2v-5b", "steps": 30}}'
```

## Manual Start / Stop

```bash
# Start
~/ComfyUI/start.sh

# Stop
launchctl stop com.portal5.comfyui

# Restart
launchctl stop com.portal5.comfyui && launchctl start com.portal5.comfyui

# View logs
tail -f ~/.portal5/logs/comfyui.log
```

## Linux (NVIDIA GPU)

```bash
# Use Docker ComfyUI with CUDA profile
./launch.sh up --profile docker-comfyui
# Models download automatically on first start
```

## Verify

```bash
curl http://localhost:8188/system_stats
# Should return JSON with GPU info showing MPS device
```

## Troubleshooting

### FLUX images are pure static / TV noise

**Do not use `--force-fp16`** with FLUX on Apple Silicon MPS. FLUX's transformer
attention layers are numerically sensitive — float16 precision errors compound over
sampling steps until the output is indistinguishable from noise. SDXL tolerates fp16
fine because its U-Net architecture is more forgiving; FLUX does not.

`~/ComfyUI/start.sh` and the LaunchAgent plist must NOT include `--force-fp16`.
ComfyUI runs FLUX in bfloat16/float32 by default on MPS, which is correct.

If you see static with FLUX but clean images from SDXL, check:
```bash
ps aux | grep "main.py" | grep -v grep   # should NOT show --force-fp16
```

If it shows `--force-fp16`, edit `~/ComfyUI/start.sh` and
`~/Library/LaunchAgents/com.portal5.comfyui.plist` to remove it, then restart
ComfyUI.