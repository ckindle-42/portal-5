# Portal 5 — UAT Results

**Run:** 2026-05-17 13:10:47  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 1
- **WARN**: 0
- **FAIL**: 0
- **SKIP**: 0
- **BLOCKED**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | PASS | [A-08 Cross-Session Memory — Two-Chat Persistence](http://localhost:8080/c/dcf01e88-74e8-4586-a035-c1a7ec34a2e6) | `auto-daily` | 6/6(100%) Chat 1: recalls region name=✓(found: ['aurora-7']); Chat 1: recalls operator name=✓(found: ['hex-lantern']); Chat 2: recalls region name=✓(found: ['aurora-7']); Chat 2: recalls operator name=✓(found: ['hex-lantern']); Chat 1 routed: auto-daily=✓(matches MLX:gemma-4-26b-a4b-it-4bit | Ollama:dolphin-llama3 — pipeline confirms: mlx-apple-silicon|mlx-community/gemma-4-26b-a4b-it-4bit); Chat 2 routed: auto-daily=✓(matches MLX:gemma-4-26b-a4b-it-4bit | Ollama:dolphin-llama3 — pipeline confirms: mlx-apple-silicon|mlx-community/gemma-4-26b-a4b-it-4bit) | 48.6s |
