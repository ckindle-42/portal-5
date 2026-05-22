# Portal 5 — ComfyUI / Image & Video Acceptance Test Results

**Run:** 2026-05-22 08:32:02 (33s)  
**Git SHA:** 28d29d6  

## Summary

- **PASS**: 6
- **Total**: 6

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | C0 | Python dependencies available | httpx, mcp, yaml all present | 0.2s |
| 2 | PASS | C0 | Portal pipeline reachable (http://localhost:9099) | HTTP 200 | 0.0s |
| 3 | PASS | C0 | ComfyUI process running on host | PIDs: 3194 | 0.0s |
| 4 | PASS | C0 | ComfyUI API reachable (http://localhost:8188) | HTTP 200 | 0.0s |
| 5 | PASS | C9 | auto-video workspace: cinematic shot description | matched 8/8 signals: ['wave', 'ocean', 'camera', 'light', 'golden', 'lens', 'focal', 'shot'] ∣ preview: **Cinematic 5‑Second Shot: Ocean Waves at Golden Hour**
 | 13.2s |
| 6 | PASS | C9 | auto-video workspace: ComfyUI workflow parameter question | matched 9/12: ['workflow', 'comfyui', 'frame', 'resolution', 'parameter', 'fps'] ∣ preview: To create a **5‑second, 4K (3840 × 2160) aerial landscape video** in | 10.4s |

## Blocked Items Register

*No blocked items.*

---
*ComfyUI outputs: check ComfyUI output/ directory*
