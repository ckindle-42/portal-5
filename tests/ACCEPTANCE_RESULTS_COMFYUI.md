# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-05-22 14:22:37 (2227s)  
**Git SHA:** 5610a41  

## Summary

- **PASS**: 8
- **Total**: 8

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.2s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 20318 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C8 | Video models available | videowan2.2 | 0.1s |
| 6 | PASS | C8 | Wan2.2: generate_video (9 frames, 832x480, 50 steps) | {
  "success": true,
  "filename": "portal_video__00074_.mp4",
  "url": "http://localhost:8188/view?filename=portal_video__00074_.mp4&type=output",
  "prompt":  | 738.9s |
| 7 | PASS | C8 | Wan2.2: generate_video (9 frames, 50 steps, different subjec | {
  "success": true,
  "filename": "portal_video__00075_.mp4",
  "url": "http://localhost:8188/view?filename=portal_video__00075_.mp4&type=output",
  "prompt":  | 738.9s |
| 8 | PASS | C8 | NSFW video: HunyuanVideo + nsfw-e7 LoRA (50 steps) | {
  "success": true,
  "filename": "portal_video__00076_.mp4",
  "url": "http://localhost:8188/view?filename=portal_video__00076_.mp4&type=output",
  "prompt":  | 739.1s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
