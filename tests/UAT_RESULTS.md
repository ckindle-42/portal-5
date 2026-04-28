# Portal 5 — UAT Results

**Run:** 2026-04-28 03:57:37  
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
| 1 | PASS | [P-DA01 Data Analyst — Correlation vs Causation](http://localhost:8080/c/410b4b85-d859-4889-898f-3644842679d3) | `dataanalyst` | 3/3(100%) Correlation/causation distinguished=✓(found: ['correlation', 'causation']); A/B test recommended=✓(found: ['instead', 'alternative', 'better to']); Does not recommend forcing=✓(found: ['backfire', 'better to offer', 'choice', 'not necessarily']) | 91.1s |
| 2 | PASS | [P-D02 Bug Discovery — Classification by Type](http://localhost:8080/c/e9a6ff19-2317-43e5-b3b9-972a91c59442) | `bugdiscoverycodeassistant` | 4/4(100%) Command injection found=✓(found: ['injection', 'os.system', 'command injection', 'shell', 'arbitrary command']); Security type label=✓(found: ['security vulnerability', 'vulnerability']); Runtime error label=✓(found: ['logic error', 'wrong data', 'crash']); At least 3 issues=✓(found: ['1.', '2.', '3.']) | 161.0s |
