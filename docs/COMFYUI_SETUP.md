# Portal 5 — ComfyUI Setup Guide

<!-- WIKI:GENERATED unit=unit-comfyui-setup-portal-5-comfyui-setup-guide -->
ComfyUI handles image generation and runs natively on the host for Metal GPU
access on Apple Silicon. Portal's video-generation service is shelved; any
video workflow material retained below is archival and not part of the
supported operating setup.
<!-- /WIKI:GENERATED -->

---

## Quick Install (Apple Silicon)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-quick-install-apple-silicon -->
```bash
./launch.sh install-comfyui
```

This clones ComfyUI to `~/ComfyUI`, installs PyTorch with MPS support,
and registers it as a launchd service that auto-starts on login.
<!-- /WIKI:GENERATED -->

---

## Download Models

<!-- WIKI:GENERATED unit=unit-comfyui-setup-download-models -->
Use `./launch.sh pull-qwen-image` to download the image-generation set verified on
Apple Silicon MPS: Qwen-Image-2512 plain FP8, Qwen-Image-Edit-2509 plain FP8,
the shared FP8-scaled text encoder and VAE, and the Lightning LoRA (about 48 GiB
total). The command installs files in ComfyUI's flat model layout and skips files
already present.

`./launch.sh download-comfyui-models` is a retired legacy alias because its old
monolithic downloader was deleted. Use the explicit family command above. Video
generation is shelved and is not part of the supported ComfyUI setup.
<!-- /WIKI:GENERATED -->

---

### Image: flux-schnell (default)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-image-flux-schnell-default -->
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
<!-- /WIKI:GENERATED -->

---

### Image: sdxl (simpler, single self-contained file, no separate CLIP/VAE needed)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-image-sdxl-simpler-single-self-contained-file-no-separate-clip-vae-needed -->
```bash
hf download stabilityai/stable-diffusion-xl-base-1.0 sd_xl_base_1.0.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
```
Set `IMAGE_BACKEND=sdxl` in `.env`.
<!-- /WIKI:GENERATED -->

---

### Archived video backend: wan21-nsfw (shelved)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-video-wan21-nsfw-currently-configured-video-backend-in-env -->
**Shelved:** `wan21-nsfw` is not a configured production backend and its
weights are not part of the supported image-only installation. Do not download
or enable it during normal setup.
<!-- /WIKI:GENERATED -->

---

### Archived activation step — do not enable

<!-- WIKI:GENERATED unit=unit-comfyui-setup-then-set-video-backend-wan21-nsfw-in-env-and-restart-docker-compose-restart-mcp-video -->
Do not set `VIDEO_BACKEND` or start `mcp-video`; video operation is shelved.
<!-- /WIKI:GENERATED -->

---

## Wan 2.2 Family (archived; service shelved)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-wan-2-2-family-v6-2-addition -->
Wan 2.2 video generation is shelved on this Apple Silicon host. The table is
retained only as an archival implementation inventory; none of these variants
is exposed as a supported Portal operation.

| Variant | Implementation state | Operating state |
|---|---|---|
| `wan22-t2v-a14b` | Workflow corrected; available FP8 checkpoints fail on MPS | SHELVED |
| `wan22-ti2v-5b` | Verified working in isolation | SHELVED by project decision |
| `wan22-animate-14b` | Stub only | NOT SUPPORTED |
| `wan22-s2v-14b` | FP8 checkpoint fails on MPS | SHELVED |

See `unit-known-limitations-wan22-fp8-scaled-checkpoints-crash-on-apple-silicon-mps`
for the evidence and revisit conditions.
<!-- /WIKI:GENERATED -->

---

### Step 1 — Pull the weights (opt-in, ~80GB total)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-step-1-pull-the-weights-opt-in-80gb-total -->
Video generation is shelved. No Wan weights are required for the supported
image-only ComfyUI setup. `./launch.sh pull-wan22` remains an explicit archival
download path for a future re-evaluation; it is not part of normal setup.
<!-- /WIKI:GENERATED -->

---

### TI2V-5B archival status

<!-- WIKI:GENERATED unit=unit-comfyui-setup-ti2v-5b-fast-image-to-video-single-file-comfyui-native-repackaging -->
**Shelved:** TI2V-5B was verified working, but the project chose not to expose
a lone partial video family. Its retained weights and workflow are archival,
not a supported setup step.
<!-- /WIKI:GENERATED -->

---

### Step 2 — Export ComfyUI workflow templates

<!-- WIKI:GENERATED unit=unit-comfyui-setup-step-2-export-comfyui-workflow-templates -->
No video workflow export is required for the supported image-only setup.
Archived workflow code remains in `portal/modules/media/tools/video_mcp.py`
for a future re-evaluation, but `mcp-video` is disabled and the unfinished
Animate/S2V paths are not supported operations.
<!-- /WIKI:GENERATED -->

---

### Step 3 — Use

<!-- WIKI:GENERATED unit=unit-comfyui-setup-step-3-use -->
```bash
<!-- /WIKI:GENERATED -->

---

### Fast preset (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-fast-preset-ti2v-5b-9-min-per-5s-clip -->
**Unavailable:** TI2V-5B worked in isolation, but video service operation is
shelved and no preset is exposed.
<!-- /WIKI:GENERATED -->

---

### Cinematic preset (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-cinematic-quality-t2v-a14b-slower -->
**Unavailable:** the T2V-A14B FP8 checkpoints fail on Apple Silicon MPS and
the video service is shelved.
<!-- /WIKI:GENERATED -->

---

### Video model override (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-explicit-model-override -->
Video model overrides are unavailable while `mcp-video` is shelved.
<!-- /WIKI:GENERATED -->

---

### Video MCP tool (unavailable)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-via-mcp-tool -->
There is no supported video MCP call. Port `8911` is disabled in normal
operation; use the image tools on `mcp-comfyui` (`8910`).
<!-- /WIKI:GENERATED -->

---

## Manual Start / Stop

<!-- WIKI:GENERATED unit=unit-comfyui-setup-manual-start-stop -->
```bash
<!-- /WIKI:GENERATED -->

---

# Start

<!-- WIKI:GENERATED unit=unit-comfyui-setup-start -->
~/ComfyUI/start.sh
<!-- /WIKI:GENERATED -->

---

# Stop

<!-- WIKI:GENERATED unit=unit-comfyui-setup-stop -->
launchctl stop com.portal5.comfyui
<!-- /WIKI:GENERATED -->

---

# Restart

<!-- WIKI:GENERATED unit=unit-comfyui-setup-restart -->
launchctl stop com.portal5.comfyui && launchctl start com.portal5.comfyui
<!-- /WIKI:GENERATED -->

---

# View logs

<!-- WIKI:GENERATED unit=unit-comfyui-setup-view-logs -->
tail -f ~/.portal5/logs/comfyui.log
```
<!-- /WIKI:GENERATED -->

---

## Linux (NVIDIA GPU)

<!-- WIKI:GENERATED unit=unit-comfyui-setup-linux-nvidia-gpu -->
```bash
<!-- /WIKI:GENERATED -->

---

# Use Docker ComfyUI with CUDA profile

<!-- WIKI:GENERATED unit=unit-comfyui-setup-use-docker-comfyui-with-cuda-profile -->
./launch.sh up --profile docker-comfyui
<!-- /WIKI:GENERATED -->

---

# Models download automatically on first start

<!-- WIKI:GENERATED unit=unit-comfyui-setup-models-download-automatically-on-first-start -->
```
<!-- /WIKI:GENERATED -->

---

## Verify

<!-- WIKI:GENERATED unit=unit-comfyui-setup-verify -->
```bash
curl http://localhost:8188/system_stats
<!-- /WIKI:GENERATED -->

---

# Should return JSON with GPU info showing MPS device

<!-- WIKI:GENERATED unit=unit-comfyui-setup-should-return-json-with-gpu-info-showing-mps-device -->
```
<!-- /WIKI:GENERATED -->

---

### FLUX images are pure static / TV noise

<!-- WIKI:GENERATED unit=unit-comfyui-setup-flux-images-are-pure-static-tv-noise -->
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
<!-- /WIKI:GENERATED -->

---
