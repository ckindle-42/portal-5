# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-06 11:07:05 (1414s)  
**Git SHA:** 75cedf4  
**Version:** 5.2.1  
**Workspaces:** 16  ·  **Personas:** 40

## Summary

- **PASS**: 28
- **INFO**: 2

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | INFO | S17 | git pull skipped (no --rebuild flag) | use --rebuild to auto-pull | 0.0s |
| 2 | INFO | S17 | Dockerfile.mcp hash | hash=9483a3c148455510641f9b851320f30f (unchanged) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 12 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 16, code has 16 | 0.0s |
| 6 | PASS | S23 | MLX watchdog disabled for testing | watchdog stopped — no false alerts during fallback tests | 0.0s |
| 7 | PASS | S23 | Pipeline health endpoint shows backend status | 7/7 backends healthy, 16 workspaces | 0.0s |
| 8 | PASS | S23 | Response includes model identity | model=mlx-community/Qwen3-Coder-Next-4bit | 68.0s |
| 9 | PASS | S23 | auto-coding: primary MLX path | model=mlx-community/Qwen3-Coder-Next-4bit | 3.3s |
| 10 | PASS | S23 | auto-coding: primary path works | model=mlx-community/Qwen3-Coder-Next-4bit | 51.5s |
| 11 | PASS | S23 | auto-coding: MLX proxy killed | MLX proxy is down | 3.7s |
| 12 | PASS | S23 | auto-coding: fallback to coding | model=qwen3-coder:30b ∣ signals=['def ', 'str', 'return', 'palindrome'] ∣ matched expected group: coding | 8.7s |
| 13 | PASS | S23 | auto-coding: MLX proxy restored | MLX proxy is back | 8.2s |
| 14 | PASS | S23 | auto-coding: MLX restored, chain intact | model=qwen3-coder:30b — chain recovered after fallback | 3.3s |
| 15 | PASS | S23 | auto-security: primary security path | model=baronllm:q6_k | 9.9s |
| 16 | PASS | S23 | auto-security: survives backend stress | model=baronllm:q6_k ∣ signals=['autoindex', 'security', 'misconfiguration'] | 5.7s |
| 17 | PASS | S23 | auto-vision: primary MLX path | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit | 63.4s |
| 18 | PASS | S23 | auto-vision: primary path works | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit | 57.2s |
| 19 | PASS | S23 | auto-vision: MLX proxy killed | MLX proxy is down | 8.3s |
| 20 | PASS | S23 | auto-vision: fallback to vision | model=deepseek-r1:32b-q4_k_m ∣ signals=['visual', 'detect', 'image', 'diagram', 'analysis'] ∣ absolute fallback (pipeline served from any healthy backend) | 26.8s |
| 21 | PASS | S23 | auto-vision: MLX proxy restored | MLX proxy is back | 8.2s |
| 22 | PASS | S23 | auto-vision: MLX restored, chain intact | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit — chain recovered after fallback | 57.1s |
| 23 | PASS | S23 | auto-reasoning: primary MLX path | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit | 65.2s |
| 24 | PASS | S23 | auto-reasoning: primary path works | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit | 68.2s |
| 25 | PASS | S23 | auto-reasoning: MLX proxy killed | MLX proxy is down | 8.3s |
| 26 | PASS | S23 | auto-reasoning: fallback to reasoning | model=deepseek-r1:32b-q4_k_m ∣ signals=['meet', 'miles', 'train', 'mph', '790'] ∣ matched expected group: reasoning | 19.9s |
| 27 | PASS | S23 | auto-reasoning: MLX proxy restored | MLX proxy is back | 8.2s |
| 28 | PASS | S23 | auto-reasoning: MLX restored, chain intact | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit — chain recovered after fallback | 56.9s |
| 29 | PASS | S23 | All backends restored and healthy | 7/7 backends healthy | 83.4s |
| 30 | PASS | S23 | All MLX workspaces survive MLX failure (8/8) | 8 responded, 0 failed (fell back to Ollama or timed out) | 112.2s |

## Blocked Items Register

*No blocked items.*

## Memory Usage Log

| Section | Free % | Used % | Notes |
|---------|--------|--------|-------|
| pre-S17 | 63% | 37% | MLX: 0.2GB free, moderate |
| pre-S23 | 63% | 37% | MLX: 0.2GB free, moderate |

---
*Screenshots: /tmp/p5_gui_*.png*
