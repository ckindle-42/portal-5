# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-04-09 17:32:47 (0s)  
**Git SHA:** b9e44b9  

## Summary

- **PASS**: 11
- **Total**: 11

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

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
