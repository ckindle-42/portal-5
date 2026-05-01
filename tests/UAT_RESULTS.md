# Portal 5 — UAT Results

**Run:** 2026-04-30 20:17:12  
**Catalog:** TEST_CATALOG (see tests/portal5_uat_driver.py)  
**Reviewer:** (fill in)

## Summary

- **PASS**: 1
- **WARN**: 0
- **FAIL**: 0
- **SKIP**: 0
- **MANUAL**: 0

## Results

| # | Status | Test | Model | Detail | Elapsed |
|---|--------|------|-------|--------|---------|
| 1 | PASS | [CC-01-laguna CC-01 Asteroids · Laguna-XS.2 (Poolside)](http://localhost:8080/c/8ed3a568-5ee4-4456-9134-63c965169e11) | `bench-laguna` | 10/10(100%) HTML file delivered=✓(code block present); Game loop (behavioral)=✓(matched: requestAnimationFrame() call); Lives manipulation (behavioral)=✓(matched: lives-- decrement); Score increment (behavioral)=✓(matched: score += (increment)); Asteroid split/push (behavioral)=✓(matched: asteroid push); Canvas game loop (keyword)=✓(found: ['requestanimationframe', 'requestAnimationFrame', 'game loop']); Asteroids split logic=✓(found: ['split', 'asteroid', 'smaller']); Lives system (keyword)=✓(found: ['lives']); Score system=✓(ok); Routed model: bench-laguna=✓(matches via workspace 'bench-laguna': MLX:laguna-xs.2-4bit | Ollama:glm-4.7-flash — pipeline confirms: mlx-apple-silicon|mlx-community/Laguna-XS.2-4bit) | 86.3s |
