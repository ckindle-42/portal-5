# Portal 5 — ComfyUI Setup Guide

ComfyUI handles image and video generation. It runs natively on the host
for Metal GPU access on Apple Silicon.

## Quick Install (Apple Silicon)

```bash
./launch.sh install-comfyui
```

This clones ComfyUI to `~/ComfyUI`, installs PyTorch with MPS support,
and registers it as a launchd service that auto-starts on login.

## Download Models

**`./launch.sh download-comfyui-models` is currently broken** — the script it called
(`scripts/download_comfyui_models.py`) was deleted in commit `ea864cf` ("superseded by
pull-wan22 / pull-qwen-image"), but those replacement subcommands were never implemented
in `launch.sh` (found during Slice P media bring-up, `TASK_MEDIA_BRINGUP_V1`). Until one of
them is rebuilt, download models directly with `hf download` / `huggingface-cli download`.

### Image: flux-schnell (default)

```bash
hf download black-forest-labs/FLUX.1-schnell flux1-schnell.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
hf download black-forest-labs/FLUX.1-schnell ae.safetensors \
    --local-dir ~/ComfyUI/models/vae/
hf download comfyanonymous/flux_text_encoders clip_l.safetensors \
    --local-dir ~/ComfyUI/models/clip/
hf download comfyanonymous/flux_text_encoders t5xxl_fp8_e4m3fn.safetensors \
    --local-dir ~/ComfyUI/models/clip/
```

Set in `.env` (or leave at these defaults — they now match `comfyui_mcp.py`):
```
IMAGE_BACKEND=flux
FLUX_CKPT_FILE=flux1-schnell.safetensors
FLUX_CLIP_L_FILE=clip_l.safetensors
FLUX_CLIP_T5_FILE=t5xxl_fp8_e4m3fn.safetensors
FLUX_VAE_FILE=ae.safetensors
```

**Do not** point `FLUX_CLIP_T5_FILE` at the raw diffusers repo's sharded
`text_encoder_2/model-00001-of-00002.safetensors` — `DualCLIPLoader` does a plain
single-file state-dict load, so a lone shard silently loads only half the T5 weights and
fails prompt validation with `Value not in list: clip_name2`. Use the single-file
ComfyUI-native repackaging (`comfyanonymous/flux_text_encoders`) above instead.

`flux-uncensored` (`Flux_v8-NSFW.safetensors` in `comfyui_mcp.py`'s `_MODEL_CKPT_MAP`) has
no currently-known working source — the old script's repo
(`enhanceaiteam/Flux-Uncensored-V2`) returns 404. Use `sdxl` or plain `flux` instead until
a source is found.

### Image: sdxl (simpler, single self-contained file, no separate CLIP/VAE needed)

```bash
hf download stabilityai/stable-diffusion-xl-base-1.0 sd_xl_base_1.0.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
```
Set `IMAGE_BACKEND=sdxl` in `.env`.

### Video: wan21-nsfw (currently configured `VIDEO_BACKEND` in `.env`)

```bash
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

**`./launch.sh pull-wan22` is advertised in `launch.sh --help` but has no implementation**
(found during Slice P media bring-up) — download directly instead:

```bash
# TI2V-5B (fast, image-to-video): single-file ComfyUI-native repackaging
hf download Comfy-Org/Wan_2.2_ComfyUI_Repackaged \
    split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors \
    split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors \
    split_files/vae/wan2.2_vae.safetensors \
    --local-dir ~/ComfyUI/models
```

T2V-A14B's weight source is not yet pinned down (see `WAN22_T2V_UNET` comment in
`video_mcp.py` — "requires separate download, not yet in pull-wan22").

### Step 2 — Export ComfyUI workflow templates

`wan22-t2v-a14b` and `wan22-ti2v-5b` already have real (non-stub) workflow dicts in
`portal/modules/media/tools/video_mcp.py` — no export needed for those two. Only
`wan22-animate-14b` and `wan22-s2v-14b` remain stubs; for those, export via ComfyUI:

1. Open ComfyUI → Workflow → Browse Templates → Video
2. Load the template ("Wan2.2-Animate-14B", "Wan2.2-S2V-14B")
3. Verify the model loads and runs a test prompt
4. Export as JSON and use the node graph to populate the corresponding `_WAN22_*_WORKFLOW` dict in `portal/modules/media/tools/video_mcp.py`

Calling `wan22-animate-14b` or `wan22-s2v-14b` before that export will raise a `RuntimeError`
with instructions. `wan22-ti2v-5b` requires an `image_url` start-frame (image-to-video, not
pure text-to-video) — `wan22-t2v-a14b` does not.

**Memory warning:** on Apple Silicon, ComfyUI does not reliably evict a previously-loaded
model's weights when a new workflow loads a different model family. Loading Flux/SDXL
(~7–27GB) and then a Wan 14B video model back-to-back in the same ComfyUI process without a
restart between them can exhaust unified memory and swap simultaneously (observed twice:
swap at 66.7GB/67.6GB used, system-locking, and separately a *tiny* job crashing free RAM
from ~45GB to ~60MB — the 14B backend's real peak usage runs well above its ~39GB on-disk
weight size, close to the entire 64GB pool regardless of frame count) — restart ComfyUI
(`launchctl kickstart -k gui/$(id -u)/com.portal5.comfyui`) between large model-family
switches. `TASK_VRAM_ADMISSION_V1` (Slice 7) added a pre-flight admission check
(`portal/modules/media/tools/_admission.py`) that refuses an oversized job with a structured
error before it OOMs — see `unit-fact-media-memory-budget` / `unit-HOWTO-media-memory-and-
launch-order`; it does not replace restarting ComfyUI between families (Tier 2 cross-engine
coordination with Ollama is explicitly not built).

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