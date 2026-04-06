# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-04-06 13:18:31 (0s)  
**Git SHA:** 98d7a63  

## Summary

- **PASS**: 7
- **Total**: 7

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.1s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 59401 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C8 | Video models available | videowan2.2 | 0.1s |
| 6 | PASS | C8 | Wan2.2: generate_video (16 frames, 832x480, 4 steps) | {
  "success": false,
  "error": "ComfyUI rejected workflow (HTTP 400): {'type': 'prompt_outputs_failed_validation', 'message': 'Prompt outputs failed validatio | 0.0s |
| 7 | PASS | C8 | Wan2.2: longer clip (32 frames, 8 steps) | {
  "success": false,
  "error": "ComfyUI rejected workflow (HTTP 400): {'type': 'prompt_outputs_failed_validation', 'message': 'Prompt outputs failed validatio | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
