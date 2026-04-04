# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-04 14:33:15 (9s)  
**Git SHA:** af128bf  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 8
- **WARN**: 1
- **INFO**: 2

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=11411af425f9e9155e27e454846ac8b5 (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 15 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | PASS | S13 | Login → chat UI loaded |  | 2.2s |
| 7 | PASS | S13 | Model dropdown shows workspace names | 16/16 visible | 0.0s |
| 8 | WARN | S13 | Personas visible | Expecting value: line 1 column 1 (char 0) | 0.0s |
| 9 | PASS | S13 | Chat textarea accepts and clears input |  | 0.0s |
| 10 | PASS | S13 | Admin panel accessible |  | 1.2s |
| 11 | PASS | S13 | MCP tool servers registered in Open WebUI | 7/7 registered: ['8910', '8911', '8912', '8913', '8914', '8915', '8916'] | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*Screenshots: /tmp/p5_gui_*.png*
