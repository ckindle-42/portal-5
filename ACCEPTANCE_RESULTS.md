# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-04 20:40:21 (0s)  
**Git SHA:** ecf265b  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 17
- **INFO**: 3

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=11411af425f9e9155e27e454846ac8b5 (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 13 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | PASS | S2 | Open WebUI |  | 0.0s |
| 7 | PASS | S2 | Pipeline |  | 0.0s |
| 8 | PASS | S2 | Grafana |  | 0.0s |
| 9 | PASS | S2 | MCP Documents |  | 0.0s |
| 10 | PASS | S2 | MCP Sandbox |  | 0.0s |
| 11 | PASS | S2 | MCP Music |  | 0.0s |
| 12 | PASS | S2 | MCP TTS |  | 0.0s |
| 13 | PASS | S2 | MCP Whisper |  | 0.0s |
| 14 | PASS | S2 | MCP Video |  | 0.0s |
| 15 | PASS | S2 | Prometheus |  | 0.0s |
| 16 | PASS | S2 | MCP ComfyUI bridge | HTTP 200 | 0.0s |
| 17 | PASS | S2 | SearXNG container | status=healthy | 0.0s |
| 18 | PASS | S2 | Ollama responding with pulled models | 20 models pulled | 0.0s |
| 19 | PASS | S2 | /metrics endpoint is unauthenticated (HOWTO §22) | HTTP 200 | 0.0s |
| 20 | INFO | S2 | MLX proxy :8081 | 15 models listed | 0.0s |

## Blocked Items Register

*No blocked items.*

---
*Screenshots: /tmp/p5_gui_*.png*
