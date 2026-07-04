---
id: unit-claude-7-all-ports-are-reserved
kind: why
title: "CLAUDE.md \u2014 7 \u2014 All Ports Are Reserved"
sources:
- type: design
  path: CLAUDE.md
  section: "7 \u2014 All Ports Are Reserved"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.808032
updated_at: 1783195000.808032
---


| Port | Service |
|---|---|
| 8080 | Open WebUI |
| 9099 | Portal Pipeline |
| 8910-8916 | MCP: ComfyUI, Video, Music, Documents, Sandbox, Whisper, TTS |
| 8917 | Embedding (Harrier-0.6B TEI) |
| 8918 | MLX speech (Kokoro + Qwen3-TTS/ASR) |
| 8919 | MCP Security |
| 8920 | MCP Memory |
| 8921 | MCP RAG |
| 8922 | MCP Research |
| 8923 | MCP Browser (Playwright) |
| 8924 | MLX Transcribe (mlx-whisper + pyannote diarization, host-native) |
| 8925 | MCP Reranker (Qwen3-Reranker-0.6B-mxfp8, MLX-native, two-stage RAG) |
| 8926 | MCP CAD Render (OpenSCAD / CadQuery 3D model generation) |
| 8928 | Pipeline MCP (host-native; exposes explore_repository + stack introspection for Claude Code / opencode) |
| 8188 | ComfyUI |
| 8088 | SearXNG |
| 11434 | Ollama |
| 9090 | Prometheus |
| 3000 | Grafana |

Port assignments are enforced in `.env.example`. Do not reassign without updating both.
