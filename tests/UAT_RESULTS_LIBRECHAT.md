# Portal 5 — UAT Results

**Run:** 2026-05-19 12:55:30  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 0
- **WARN**: 0
- **FAIL**: 1
- **SKIP**: 0
- **BLOCKED**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | FAIL | [A-08 Cross-Session Memory — Two-Chat Persistence](http://localhost:8082/c/new?endpoint=Portal+5&model=auto-daily) | `auto-daily` | 4/6(66%) [routed: mlx-apple-silicon|mlx-community/gemma-4-26b-a4b-it-4bit] Chat 1: recalls region name=✓(found: ['aurora-7']); Chat 1: recalls operator name=✓(found: ['hex-lantern']); Chat 2: recalls region name=✗(none of: ['aurora-7', 'aurora 7', 'aurora7']); Chat 2: recalls operator name=✗(none of: ['hex-lantern', 'hex lantern', 'hexlantern']); Chat 1 routed: mlx-apple-silicon|mlx-communit=✓(matches MLX:gemma-4-26b-a4b-it-4bit | Ollama:dolphin-llama3 — pipeline confirms: mlx-apple-silicon|mlx-community/gemma-4-26b-a4b-it-4bit); Chat 2 routed: mlx-apple-silicon|mlx-communit=✓(matches MLX:gemma-4-26b-a4b-it-4bit | Ollama:dolphin-llama3 — pipeline confirms: mlx-apple-silicon|mlx-community/gemma-4-26b-a4b-it-4bit) | 76.1s |
