# Portal 5 — UAT Results

**Run:** 2026-05-04 07:39:20  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 2
- **WARN**: 0
- **FAIL**: 0
- **SKIP**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | PASS | [T-08 Image Generation — ComfyUI FLUX](http://localhost:8080/c/5bebfc87-a60c-4319-8ed2-d14bd00dd12d) | `auto` | 3/3(100%) No error=✓(ok); PNG ≥512px=✓(1024x1024, 680694 bytes); Routed model: auto=✓(matches MLX:dolphin3.0-llama3.1-8b-8bit | Ollama:dolphin-llama3 — pipeline confirms: mlx-apple-silicon|mlx-community/Dolphin3.0-Llama3.1-8B-8bit) | 291.7s |
| 2 | PASS | [WS-11 Video Creator — Storm Timelapse](http://localhost:8080/c/f7941ab8-7fa2-4652-ab4d-3dc707da9078) | `auto-video` | 4/4(100%) No error=✓(ok); MP4 ≥1s=✓(1.1s, 577032 bytes); Recovery: passed on attempt 3/3=✓(2 retries needed (backend instability signal)); Routed model: auto-video=✓(matches Ollama:granite4.1 — pipeline confirms: ollama-general|granite4.1:8b) | 916.1s |
