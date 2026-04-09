# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-04-09 18:15:22 (2520s)  
**Git SHA:** 8544b79  

## Summary

- **PASS**: 37
- **INFO**: 1
- **Total**: 38

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.2s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 33781 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C1 | ComfyUI system_stats | Python 3.14.3 (main, Feb  3 2026, 15:32:20) [Clang 17.0.0 (clang-1700.6.3.2)], ComfyUI version ? | 0.0s |
| 6 | PASS | C1 | ComfyUI /queue reachable | running=0 pending=0 | 0.0s |
| 7 | PASS | C1 | ComfyUI /object_info (node catalogue) | 646 nodes registered | 0.1s |
| 8 | PASS | C1 | Checkpoint models installed | 5 checkpoint(s): Flux_v8-NSFW.safetensors, flux1-dev.safetensors, flux1-schnell.safetensors, lora.safetensors, sd_xl_base_1.0.safetensors | 0.0s |
| 9 | PASS | C1 | VAE models installed | 3 VAE(s): ae.safetensors, hunyuan_video_vae_bf16.safetensors, pixel_space | 0.0s |
| 10 | PASS | C1 | LoRA models installed | 2 LoRA(s): flux_dev_frostinglane_araminta_k.safetensors, nsfw-e7.safetensors | 0.0s |
| 11 | PASS | C1 | Upscale models installed | 1 upscaler(s): RealESRGAN_x4.pth | 0.0s |
| 12 | PASS | C2 | ComfyUI MCP bridge (:8910) | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 13 | PASS | C2 | Video MCP bridge (:8911) | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 14 | PASS | C2 | ComfyUI+video MCP containers running | portal5-mcp-comfyui=running, portal5-mcp-video=running | 0.2s |
| 15 | PASS | C3 | list_workflows returns checkpoint list | workflows/checkpoints: Flux_v8-NSFW.safetensorsflux1-dev.safetensorsflux1-schnell.safetensorslora.safetensorssd_xl_base_1.0.safetensors | 0.2s |
| 16 | PASS | C3 | list_video_models returns model list | video models: videowan2.2 | 0.0s |
| 17 | PASS | C3 | list_samplers returns sampler list | Unknown tool: list_samplers | 0.0s |
| 18 | PASS | C4 | FLUX schnell checkpoint installed | flux1-schnell.safetensors | 0.1s |
| 19 | PASS | C4 | FLUX schnell: generate_image (4 steps) | {
  "success": true,
  "filename": "portal__00118_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00118_.png&type=output",
  "prompt": " | 84.9s |
| 20 | PASS | C4 | FLUX schnell output accessible via /view | portal__00118_.png — HTTP 200 | 0.0s |
| 21 | PASS | C5 | FLUX dev checkpoint installed | flux1-dev.safetensors | 0.1s |
| 22 | PASS | C5 | FLUX dev: generate_image (20 steps, cfg=3.5) | {
  "success": true,
  "filename": "portal__00119_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00119_.png&type=output",
  "prompt": " | 546.7s |
| 23 | PASS | C5 | LoRA generation: flux_dev_frostinglane_araminta_k.safetensor | {
  "success": true,
  "filename": "portal__00120_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00120_.png&type=output",
  "prompt": " | 57.6s |
| 24 | PASS | C5 | LoRA generation: nsfw-e7.safetensors (NSFW) | {
  "success": true,
  "filename": "portal__00121_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00121_.png&type=output",
  "prompt": " | 57.5s |
| 25 | PASS | C6 | SDXL checkpoint installed | sd_xl_base_1.0.safetensors | 0.1s |
| 26 | PASS | C6 | SDXL: generate_image (25 steps, cfg=7, 1024x1024) | {
  "success": true,
  "filename": "portal__00122_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00122_.png&type=output",
  "prompt": " | 541.7s |
| 27 | INFO | C7 | Parameter sweep using checkpoint | using: flux1-schnell.safetensors | 0.1s |
| 28 | PASS | C7 | Seed determinism: seed=1234 run 1 | {
  "success": true,
  "filename": "portal__00123_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00123_.png&type=output",
  "prompt": " | 58.6s |
| 29 | PASS | C7 | Step variation: 8 steps (same seed) | {
  "success": true,
  "filename": "portal__00124_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00124_.png&type=output",
  "prompt": " | 110.0s |
| 30 | PASS | C7 | Negative prompt: portrait with exclusions | {
  "success": true,
  "filename": "portal__00125_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00125_.png&type=output",
  "prompt": " | 58.6s |
| 31 | PASS | C8 | Video models available | videowan2.2 | 0.0s |
| 32 | PASS | C8 | Wan2.2: generate_video (16 frames, 832x480, 4 steps) | {
  "success": true,
  "filename": "portal_video__00025_.mp4",
  "url": "http://host.docker.internal:8188/view?filename=portal_video__00025_.mp4&type=output",
  | 239.1s |
| 33 | PASS | C8 | Wan2.2: longer clip (32 frames, 8 steps) | {
  "success": true,
  "filename": "portal_video__00026_.mp4",
  "url": "http://host.docker.internal:8188/view?filename=portal_video__00026_.mp4&type=output",
  | 757.6s |
| 34 | PASS | C9 | auto-video workspace: cinematic shot description | matched 7/8 signals: ['wave', 'ocean', 'camera', 'light', 'golden', 'lens', 'focal'] ∣ preview: Camera angle: Wide angle
Lens focal length: 16-35mm
Lighting: Wa | 4.5s |
| 35 | PASS | C9 | auto-video workspace: ComfyUI workflow parameter question | matched 7/12: ['workflow', 'comfyui', 'frame', 'resolution', 'parameter', 'fps'] ∣ preview: For a 5-second 4K aerial landscape video with smooth motion, I'd rec | 2.5s |
| 36 | PASS | C10 | Recent outputs in ComfyUI /history | 8 image(s), 2 video(s) in recent history | 0.0s |
| 37 | PASS | C10 | Latest image accessible and valid | portal__00125_.png: 1172.1KB, image/png | 0.0s |
| 38 | PASS | C10 | Latest video accessible and valid | portal_video__00026_.mp4: 0.89MB, video/mp4 | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
