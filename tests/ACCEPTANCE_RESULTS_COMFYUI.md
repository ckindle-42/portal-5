# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-05-22 10:15:40 (447s)  
**Git SHA:** f8afcf0  

## Summary

- **PASS**: 7
- **INFO**: 1
- **Total**: 8

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.2s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 3194 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C11 | LoRA inventory | 2 LoRA(s) installed: flux_dev_frostinglane_araminta_k.safetensors, nsfw-e7.safetensors | 0.1s |
| 6 | INFO | C11 | LoRA base models | schnell=flux1-schnell.safetensors, dev=flux1-dev.safetensors | 0.0s |
| 7 | PASS | C11 | LoRA: flux_dev_frostinglane_araminta_k.safetensors (20s, flu | {
  "success": true,
  "filename": "portal__00192_.png",
  "url": "http://localhost:8188/view?filename=portal__00192_.png&type=output",
  "prompt": "portrait of | 340.8s |
| 8 | PASS | C11 | LoRA: nsfw-e7.safetensors (4s, flux1-schnell.safete) | {
  "success": true,
  "filename": "portal__00193_.png",
  "url": "http://localhost:8188/view?filename=portal__00193_.png&type=output",
  "prompt": "nsfwsks, ph | 96.5s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
