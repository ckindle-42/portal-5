# Portal 5 — Acceptance Test Results (v4)

**Run:** 2026-04-08 16:30:27 (2s)  
**Git SHA:** c2d0d63  
**Version:** 6.0.0  
**Workspaces:** 17  ·  **Personas:** 40

## Summary

- **PASS**: 37

## All Results

| # | Status | Section | Test | Detail | Duration |
|---|--------|---------|------|--------|----------|
| 1 | PASS | S17 | MCP image staleness check | all images newer than last source commit (4c0665d 2026-04-08 12:52:10 -0500) | 0.1s |
| 2 | PASS | S17 | MLX proxy deployed vs repo | deployed matches repo (hash=b554d523) | 0.0s |
| 3 | PASS | S17 | All MCP services healthy — no restart needed |  | 0.0s |
| 4 | PASS | S17 | All expected containers running | 12 containers up | 0.1s |
| 5 | PASS | S17 | Pipeline /health workspace count matches codebase | pipeline reports 17, code has 17 | 0.0s |
| 6 | PASS | S0 | Git repo reachable and HEAD resolved | sha=c2d0d63 | 0.0s |
| 7 | PASS | S0 | Codebase matches remote main | local=c2d0d63 remote=c2d0d63 | 0.0s |
| 8 | PASS | S0 | Pipeline /health version fields | version=dev workspaces=17 backends_healthy=7 | 0.0s |
| 9 | PASS | S0 | portal-5 package installed | v6.0.0 | 0.0s |
| 10 | PASS | S1 | router_pipe.py WORKSPACES ↔ backends.yaml workspace_routing |  | 0.0s |
| 11 | PASS | S1 | All 40 persona YAMLs have required fields |  | 0.0s |
| 12 | PASS | S1 | update_workspace_tools.py covers all workspace IDs | all 17 covered | 0.0s |
| 13 | PASS | S1 | docker-compose.yml is valid YAML |  | 0.0s |
| 14 | PASS | S1 | imports/openwebui/mcp-servers.json present and non-empty | 4 entries | 0.0s |
| 15 | PASS | S1 | mlx-proxy.py: Gemma 4 31B dense in ALL_MODELS and VLM_MODELS | ✓ present in both | 0.0s |
| 16 | PASS | S1 | mlx-proxy.py: Magistral in ALL_MODELS but NOT in VLM_MODELS  | ✓ mlx_lm routing correct | 0.0s |
| 17 | PASS | S1 | config/routing_descriptions.json — 15 workspaces described | all routable workspaces described | 0.0s |
| 18 | PASS | S1 | config/routing_examples.json — 30 examples | 30 examples, all well-formed | 0.0s |
| 19 | PASS | S1 | mlx-proxy.py MODEL_MEMORY covers all 16 models in ALL_MODELS | all models have memory estimates | 0.0s |
| 20 | PASS | S1 | LLM intent router wired into router_pipe.py (P5-FUT-006) | LLM router present, wired, keyword fallback retained, env var documented | 0.0s |
| 21 | PASS | S14 | No stale 'Click + enable' instructions |  | 0.0s |
| 22 | PASS | S14 | §3 workspace table has 17 rows | table rows=17, code has 17 | 0.0s |
| 23 | PASS | S14 | auto-compliance workspace documented in §3 |  | 0.0s |
| 24 | PASS | S14 | Persona count claim matches YAML file count | claimed=40, yaml files=40 | 0.0s |
| 25 | PASS | S14 | §16 Telegram workspace list complete | all IDs listed | 0.0s |
| 26 | PASS | S14 | §11 TTS backend is kokoro as documented | actual: {'status': 'ok', 'service': 'tts-mcp', 'backend': 'kokoro', 'voice_cloning': False} | 0.0s |
| 27 | PASS | S14 | HOWTO §3 curl command works | HTTP 200 | 0.0s |
| 28 | PASS | S14 | HOWTO §5 curl command works | HTTP 200 | 0.0s |
| 29 | PASS | S14 | HOWTO §7 curl command works | HTTP 200 | 0.0s |
| 30 | PASS | S14 | HOWTO §22 curl command works | HTTP 200 | 0.0s |
| 31 | PASS | S14 | §12 whisper health via docker exec (exact HOWTO command) | {"status":"ok","service":"whisper-mcp"} | 0.0s |
| 32 | PASS | S14 | HOWTO footer version matches pyproject.toml (6.0.0) | expected 6.0.0 in HOWTO footer | 0.0s |
| 33 | PASS | S14 | HOWTO MLX table documents gemma-4-31b-it-4bit | found | 0.0s |
| 34 | PASS | S14 | HOWTO MLX table documents Magistral-Small-2509-MLX-8bit | found | 0.0s |
| 35 | PASS | S14 | HOWTO documents auto-spl workspace | found | 0.0s |
| 36 | PASS | S14 | .env.example documents ENABLE_REMOTE_ACCESS | found | 0.0s |
| 37 | PASS | S14 | .env.example documents LLM_ROUTER_ENABLED (P5-FUT-006) | found | 0.0s |

## Blocked Items Register

*No blocked items.*

## Memory Usage Log

| Section | Free % | Used % | Notes |
|---------|--------|--------|-------|
| pre-S17 | 94% | 6% | MLX: 12.3GB free, normal |
| pre-S0 | 94% | 6% | MLX: 12.3GB free, normal |
| pre-S1 | 94% | 6% | MLX: 12.3GB free, normal |
| pre-S14 | 94% | 6% | MLX: 12.3GB free, normal |

---
*Screenshots: /tmp/p5_gui_*.png*
