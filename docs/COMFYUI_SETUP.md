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

### Video Generation Workflow

The Video MCP (`portal_mcp/video/video_mcp.py`) communicates with ComfyUI via API to generate videos:

1. **ComfyUI must be running** at `http://localhost:8188`
2. **Wan2.2 model must be downloaded** to `~/ComfyUI/models/checkpoints/`
3. **Video MCP service** in docker-compose connects to ComfyUI
4. **User requests video** via Open WebUI Tools panel

To test video generation manually:
```bash
# Check ComfyUI API is accessible
curl http://localhost:8188/system_stats

# Check available models
curl http://localhost:8188/object_info/ComfyUINode
```

**Note**: Video generation is resource-intensive. On Apple Silicon (M-series Macs), expect:
- Wan2.2 T2V: 5-15 minutes per video
- Requires ~12GB unified memory available

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
