# Portal 5.0 — ComfyUI Setup Guide

ComfyUI handles image and video generation. It runs **outside Docker** on the host
machine to access GPU/MPS hardware directly.

## Installation (macOS — Apple Silicon)

```bash
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI
pip install -r requirements.txt
```

Start ComfyUI (add to a startup script or run in a terminal before `./launch.sh up`):
```bash
cd ~/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
# For MPS (Apple Silicon): python main.py --listen 0.0.0.0 --port 8188 --force-fp16
```

## Model Downloads

Place all models in `~/ComfyUI/models/checkpoints/` (create directory if needed).

### FLUX.1-schnell (Fast image generation — recommended first install)
```bash
pip install huggingface_hub
huggingface-cli download black-forest-labs/FLUX.1-schnell \
    flux1-schnell.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
```

### FLUX.1-dev (Higher quality, requires HuggingFace token)
```bash
huggingface-cli login  # Enter your HF_TOKEN
huggingface-cli download black-forest-labs/FLUX.1-dev \
    flux1-dev.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
```

### SDXL Base 1.0 (Alternative — no token required)
```bash
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
    sd_xl_base_1.0.safetensors \
    --local-dir ~/ComfyUI/models/checkpoints/
```

### Wan2.2 (Text-to-video — 5B model, requires ~12GB VRAM)
```bash
huggingface-cli download Wan-AI/Wan2.2-T2V-5B \
    --local-dir ~/ComfyUI/models/checkpoints/
```

## Open WebUI Configuration

Once ComfyUI is running at `http://localhost:8188`:

1. Log in to Open WebUI as admin
2. Go to **Admin Panel > Settings > Images**
3. Enable **Image Generation**
4. Set engine to **ComfyUI**
5. Set URL to `http://host.docker.internal:8188`
6. Select a default model from the dropdown

## Testing

In a chat, type: `Generate an image of a futuristic city at sunset`

The image should appear inline in the chat response.
