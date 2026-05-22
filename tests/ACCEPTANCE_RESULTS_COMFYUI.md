# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-05-22 13:08:23 (1424s)  
**Git SHA:** c7cd6ca  

## Summary

- **PASS**: 10
- **INFO**: 2
- **Total**: 12

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.2s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 20318 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C5 | FLUX dev checkpoint installed | flux1-dev.safetensors | 0.1s |
| 6 | PASS | C5 | FLUX dev: generate_image (28 steps, cfg=3.5) | {
  "success": true,
  "filename": "portal__00200_.png",
  "url": "http://localhost:8188/view?filename=portal__00200_.png&type=output",
  "prompt": "mountain la | 347.7s |
| 7 | PASS | C5 | LoRA generation: flux_dev_frostinglane_araminta_k.safetensor | {
  "success": true,
  "filename": "portal__00201_.png",
  "url": "http://localhost:8188/view?filename=portal__00201_.png&type=output",
  "prompt": "portrait of | 349.0s |
| 8 | PASS | C5 | NSFW checkpoint: Flux_v8-NSFW.safetensors (28 steps) | {
  "success": true,
  "filename": "portal__00202_.png",
  "url": "http://localhost:8188/view?filename=portal__00202_.png&type=output",
  "prompt": "nsfwsks, ar | 341.2s |
| 9 | PASS | C11 | LoRA inventory | 2 LoRA(s) installed: flux_dev_frostinglane_araminta_k.safetensors, nsfw-e7.safetensors | 0.1s |
| 10 | INFO | C11 | LoRA base models | schnell=flux1-schnell.safetensors, dev=flux1-dev.safetensors | 0.0s |
| 11 | PASS | C11 | LoRA: flux_dev_frostinglane_araminta_k.safetensors (28s, flu | {
  "success": true,
  "filename": "portal__00203_.png",
  "url": "http://localhost:8188/view?filename=portal__00203_.png&type=output",
  "prompt": "portrait of | 375.7s |
| 12 | INFO | C11 | LoRA: nsfw-e7.safetensors | video-only LoRA — skipped for image generation (tested in C8) | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
