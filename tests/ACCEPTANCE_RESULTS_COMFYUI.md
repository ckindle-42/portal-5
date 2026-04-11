# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-04-09 19:13:51 (2733s)  
**Git SHA:** 9d4cb9f  

## Summary

- **PASS**: 38
- **INFO**: 1
- **Total**: 39

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
| 15 | PASS | C3 | list_workflows returns checkpoint list | workflows/checkpoints: Flux_v8-NSFW.safetensorsflux1-dev.safetensorsflux1-schnell.safetensorslora.safetensorssd_xl_base_1.0.safetensors | 0.1s |
| 16 | PASS | C3 | list_video_models returns model list | video models: videowan2.2 | 0.0s |
| 17 | PASS | C3 | list_samplers returns sampler list | Unknown tool: list_samplers | 0.0s |
| 18 | PASS | C4 | FLUX schnell checkpoint installed | flux1-schnell.safetensors | 0.1s |
| 19 | PASS | C4 | FLUX schnell: generate_image (4 steps) | {
  "success": true,
  "filename": "portal__00126_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00126_.png&type=output",
  "prompt": " | 84.8s |
| 20 | PASS | C4 | FLUX schnell output accessible via /view | portal__00126_.png — HTTP 200 | 0.0s |
| 21 | PASS | C5 | FLUX dev checkpoint installed | flux1-dev.safetensors | 0.1s |
| 22 | PASS | C5 | FLUX dev: generate_image (20 steps, cfg=3.5) | {
  "success": true,
  "filename": "portal__00127_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00127_.png&type=output",
  "prompt": " | 547.8s |
| 23 | PASS | C5 | LoRA generation: flux_dev_frostinglane_araminta_k.safetensor | {
  "success": true,
  "filename": "portal__00128_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00128_.png&type=output",
  "prompt": " | 57.6s |
| 24 | PASS | C5 | NSFW checkpoint: Flux_v8-NSFW.safetensors | {
  "success": true,
  "filename": "portal__00129_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00129_.png&type=output",
  "prompt": " | 57.2s |
| 25 | PASS | C6 | SDXL checkpoint installed | sd_xl_base_1.0.safetensors | 0.1s |
| 26 | PASS | C6 | SDXL: generate_image (25 steps, cfg=7, 1024x1024) | {
  "success": true,
  "filename": "portal__00130_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00130_.png&type=output",
  "prompt": " | 541.7s |
| 27 | INFO | C7 | Parameter sweep using checkpoint | using: flux1-schnell.safetensors | 0.1s |
| 28 | PASS | C7 | Seed determinism: seed=1234 run 1 | {
  "success": true,
  "filename": "portal__00131_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00131_.png&type=output",
  "prompt": " | 58.6s |
| 29 | PASS | C7 | Step variation: 8 steps (same seed) | {
  "success": true,
  "filename": "portal__00132_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00132_.png&type=output",
  "prompt": " | 110.1s |
| 30 | PASS | C7 | Negative prompt: portrait with exclusions | {
  "success": true,
  "filename": "portal__00133_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00133_.png&type=output",
  "prompt": " | 58.5s |
| 31 | PASS | C8 | Video models available | videowan2.2 | 0.0s |
| 32 | PASS | C8 | Wan2.2: generate_video (16 frames, 832x480, 4 steps) | {
  "success": true,
  "filename": "portal_video__00027_.mp4",
  "url": "http://host.docker.internal:8188/view?filename=portal_video__00027_.mp4&type=output",
  | 245.2s |
| 33 | PASS | C8 | Wan2.2: longer clip (32 frames, 8 steps) | {
  "success": true,
  "filename": "portal_video__00028_.mp4",
  "url": "http://host.docker.internal:8188/view?filename=portal_video__00028_.mp4&type=output",
  | 769.6s |
| 34 | PASS | C8 | NSFW video: HunyuanVideo + nsfw-e7 LoRA (trigger: nsfwsks) | {
  "success": true,
  "filename": "portal_video__00029_.mp4",
  "url": "http://host.docker.internal:8188/view?filename=portal_video__00029_.mp4&type=output",
  | 197.0s |
| 35 | PASS | C9 | auto-video workspace: cinematic shot description | matched 8/8 signals: ['wave', 'ocean', 'camera', 'light', 'golden', 'lens', 'focal', 'shot'] ∣ preview: Camera angle: Eye-level

Lens focal length: 50mm

Lighti | 2.7s |
| 36 | PASS | C9 | auto-video workspace: ComfyUI workflow parameter question | matched 7/12: ['workflow', 'comfyui', 'frame', 'resolution', 'parameter', 'fps'] ∣ preview: To create a smooth, 4K aerial landscape video, consider using these  | 2.0s |
| 37 | PASS | C10 | Recent outputs in ComfyUI /history | 7 image(s), 3 video(s) in recent history | 0.0s |
| 38 | PASS | C10 | Latest image accessible and valid | portal__00133_.png: 1172.1KB, image/png | 0.0s |
| 39 | PASS | C10 | Latest video accessible and valid | portal_video__00029_.mp4: 0.65MB, video/mp4 | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
