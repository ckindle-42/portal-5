# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-09 11:01:50 (1140s)  
**Git SHA:** e709329  
**Version:** 6.0.0  
**Workspaces:** 17  ·  **Personas:** 40

## Summary

- **PASS**: 29
- **WARN**: 1

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | S17 | MCP image staleness check | all images newer than last source commit (4c0665d 2026-04-08 12:52:10 -0500) | 0.1s |
| 2 | PASS | S17 | MLX proxy deployed vs repo | deployed matches repo (hash=b554d523) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 12 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 17, code has 17 | 0.0s |
| 6 | PASS | S23 | MLX watchdog confirmed disabled for fallback tests | watchdog killed at startup and confirmed absent before kill/restore cycles | 0.0s |
| 7 | PASS | S23 | Pipeline health endpoint shows backend status | 7/7 backends healthy, 17 workspaces | 0.0s |
| 8 | PASS | S23 | Response includes model identity | model=mlx-community/Qwen3-Coder-Next-4bit | 1.3s |
| 9 | PASS | S23 | auto-coding: primary MLX path | model=lmstudio-community/Devstral-Small-2507-MLX-4bit | 50.2s |
| 10 | PASS | S23 | auto-coding: primary path works | model=lmstudio-community/Devstral-Small-2507-MLX-4bit | 11.4s |
| 11 | PASS | S23 | auto-coding: MLX proxy killed | MLX proxy is down | 3.7s |
| 12 | PASS | S23 | auto-coding: fallback to coding | model=deepseek-r1:32b-q4_k_m ∣ signals=['str', 'return', 'palindrome', 'complexity'] ∣ absolute fallback (pipeline served from any healthy backend) | 29.6s |
| 13 | PASS | S23 | auto-coding: MLX proxy restored | MLX proxy is back | 8.3s |
| 14 | PASS | S23 | auto-coding: MLX restored, chain intact | model=dolphin-llama3:8b — chain recovered after fallback | 4.8s |
| 15 | PASS | S23 | auto-security: primary security path | model=baronllm:q6_k | 9.8s |
| 16 | PASS | S23 | auto-security: survives backend stress | model=baronllm:q6_k ∣ signals=['autoindex', 'security', 'misconfiguration', 'expose'] | 5.6s |
| 17 | PASS | S23 | auto-vision: primary MLX path | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit | 64.8s |
| 18 | PASS | S23 | auto-vision: primary path works | model=Jackrong/MLX-Qwopus3.5-27B-v3-8bit | 24.7s |
| 19 | PASS | S23 | auto-vision: MLX proxy killed | MLX proxy is down | 8.3s |
| 20 | PASS | S23 | auto-vision: fallback to vision | model=deepseek-r1:32b-q4_k_m ∣ signals=['visual', 'describe', 'image', 'diagram', 'analysis'] ∣ absolute fallback (pipeline served from any healthy backend) | 27.1s |
| 21 | PASS | S23 | auto-vision: MLX proxy restored | MLX proxy is back | 8.3s |
| 22 | PASS | S23 | auto-vision: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 3.6s |
| 23 | PASS | S23 | auto-reasoning: primary MLX path | model=deepseek-r1:32b-q4_k_m (admission rejected — memory constrained, Ollama fallback correct) | 17.6s |
| 24 | PASS | S23 | auto-reasoning: primary path works | model=deepseek-r1:32b-q4_k_m | 17.3s |
| 25 | PASS | S23 | auto-reasoning: MLX proxy killed | MLX proxy is down | 8.3s |
| 26 | PASS | S23 | auto-reasoning: fallback to reasoning | model=deepseek-r1:32b-q4_k_m ∣ signals=['meet', 'hour', 'miles', 'train', 'mph', '790'] ∣ matched expected group: reasoning | 17.2s |
| 27 | PASS | S23 | auto-reasoning: MLX proxy restored | MLX proxy is back | 8.3s |
| 28 | PASS | S23 | auto-reasoning: MLX restored, chain intact | model=deepseek-r1:32b-q4_k_m — chain recovered after fallback | 17.1s |
| 29 | WARN | S23 | All backends restored and healthy | 6/7 backends healthy | 130.8s |
| 30 | PASS | S23 | All MLX workspaces survive MLX failure (8/8) | 8 responded, 0 failed (fell back to Ollama or timed out) | 125.3s |

## Blocked Items Register

*No blocked items.*

## Memory Usage Log

| Section | Free % | Used % | Notes |
|---------|--------|--------|-------|
| pre-S17 | 95% | 5% | MLX: 0.1GB free, normal |
| pre-S23 | 95% | 5% | MLX: 0.1GB free, normal |

---
*Screenshots: /tmp/p5_gui_*.png*
