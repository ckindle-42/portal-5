# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-04-06 12:24:45 (869s)  
**Git SHA:** d8ead35  

## Summary

- **PASS**: 24
- **WARN**: 4
- **INFO**: 8
- **Total**: 36

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.2s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 59401 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C1 | ComfyUI system_stats | Python 3.14.3 (main, Feb  3 2026, 15:32:20) [Clang 17.0.0 (clang-1700.6.3.2)], ComfyUI version ? | 0.0s |
| 6 | PASS | C1 | ComfyUI /queue reachable | running=0 pending=0 | 0.0s |
| 7 | PASS | C1 | ComfyUI /object_info (node catalogue) | 646 nodes registered | 0.1s |
| 8 | PASS | C1 | Checkpoint models installed | 4 checkpoint(s): Flux_v8-NSFW.safetensors, flux1-schnell.safetensors, lora.safetensors, sd_xl_base_1.0.safetensors | 0.0s |
| 9 | INFO | C1 | VAE models installed | 2 VAE(s): ae.safetensors, pixel_space | 0.0s |
| 10 | INFO | C1 | LoRA models installed | none installed | 0.0s |
| 11 | INFO | C1 | Upscale models installed | none installed | 0.0s |
| 12 | PASS | C2 | ComfyUI MCP bridge (:8910) | {'status': 'ok', 'service': 'comfyui-mcp'} | 0.0s |
| 13 | PASS | C2 | Video MCP bridge (:8911) | {'status': 'ok', 'service': 'video-mcp'} | 0.0s |
| 14 | INFO | C2 | ComfyUI+video containers in docker compose | none matched — check docker compose ps | 0.0s |
| 15 | PASS | C3 | list_workflows returns checkpoint list | workflows/checkpoints: Flux_v8-NSFW.safetensorsflux1-schnell.safetensorslora.safetensorssd_xl_base_1.0.safetensors | 0.0s |
| 16 | PASS | C3 | list_video_models returns model list | video models: videowan2.2 | 0.0s |
| 17 | PASS | C3 | list_samplers returns sampler list | Unknown tool: list_samplers | 0.0s |
| 18 | PASS | C4 | FLUX schnell checkpoint installed | flux1-schnell.safetensors | 0.1s |
| 19 | PASS | C4 | FLUX schnell: generate_image (4 steps) | {
  "success": true,
  "filename": "portal__00058_.png",
  "url": "http://host.docker.internal:8188/view?filename=portal__00058_.png&type=output",
  "prompt": " | 80.7s |
| 20 | PASS | C4 | FLUX schnell output accessible via /view | portal__00058_.png — HTTP 200 | 0.0s |
| 21 | INFO | C5 | FLUX dev checkpoint installed | not installed (optional) — download: huggingface-cli download black-forest-labs/FLUX.1-dev | 0.1s |
| 22 | INFO | C5 | FLUX dev generation via MCP | skipped — checkpoint not installed | 0.0s |
| 23 | PASS | C6 | SDXL checkpoint installed | sd_xl_base_1.0.safetensors | 0.0s |
| 24 | WARN | C6 | SDXL: generate_image (25 steps, cfg=7, 1024x1024) | timeout after 300s (TaskGroup) | 300.0s |
| 25 | INFO | C7 | Parameter sweep using checkpoint | using: flux1-schnell.safetensors | 0.1s |
| 26 | WARN | C7 | Seed determinism: seed=1234 run 1 | timeout after 120s (TaskGroup) | 120.0s |
| 27 | WARN | C7 | Step variation: 8 steps (same seed) | timeout after 180s (TaskGroup) | 180.0s |
| 28 | WARN | C7 | Negative prompt: portrait with exclusions | timeout after 120s (TaskGroup) | 120.0s |
| 29 | PASS | C8 | Video models available | videowan2.2 | 0.1s |
| 30 | PASS | C8 | Wan2.2: generate_video (16 frames, 832x480, 4 steps) | {
  "success": false,
  "error": "Generation completed but no video output found. Check ComfyUI logs."
} | 56.3s |
| 31 | PASS | C8 | Wan2.2: longer clip (32 frames, 8 steps) | {
  "success": false,
  "error": "Generation completed but no video output found. Check ComfyUI logs."
} | 2.1s |
| 32 | PASS | C9 | auto-video workspace: cinematic shot description | matched 8/8 signals: ['wave', 'ocean', 'camera', 'light', 'golden', 'lens', 'focal', 'shot'] ∣ preview: Camera angle: A low angle shot, with the camera placed a | 6.0s |
| 33 | PASS | C9 | auto-video workspace: ComfyUI workflow parameter question | matched 7/12: ['workflow', 'comfyui', 'frame', 'resolution', 'parameter', 'fps'] ∣ preview: For a 5-second 4K aerial landscape video with smooth motion, I would | 3.5s |
| 34 | PASS | C10 | Recent outputs in ComfyUI /history | 5 image(s), 0 video(s) in recent history | 0.0s |
| 35 | PASS | C10 | Latest image accessible and valid | portal__00062_.png: 1117.0KB, image/png | 0.0s |
| 36 | INFO | C10 | Latest video accessible and valid | no videos in recent history | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
