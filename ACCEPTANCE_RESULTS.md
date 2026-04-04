# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-03 18:20:48 (139s)  
**Git SHA:** 40750d2  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 5
- **INFO**: 2

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=11411af425f9e9155e27e454846ac8b5 (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 15 containers up | 0.3s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | PASS | S15 | SearXNG /search?format=json returns results | 39 results for 'NERC CIP' | 3.1s |
| 7 | PASS | S15 | auto-research workspace: technical comparison response | signals: ['aes', 'rsa', 'symmetric', 'asymmetric', 'key'] | 133.9s |

## Blocked Items Register

*No blocked items.*

---
*Screenshots: /tmp/p5_gui_*.png*
