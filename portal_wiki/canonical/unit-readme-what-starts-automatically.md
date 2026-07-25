---
id: unit-readme-what-starts-automatically
kind: what
title: "README \u2014 What Starts Automatically"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: What Starts Automatically
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.678988
updated_at: 1784946220.678988
---

Everything runs with a single command. No manual configuration.

| Service | What it does | URL |
|---|---|---|
| Open WebUI | Chat interface — your main portal | http://localhost:8080 |
| Portal Pipeline | Intelligent routing, auth, metrics | :9099 (internal) |
| Ollama | Runs local GGUF models via Metal | :11434 (internal) |
| SearXNG | Private web search for research | (internal) |
| ComfyUI | Image and video generation (host-native) | http://localhost:8188 |
| MCP Servers (14) | ComfyUI (:8910), Video (:8911), Music (:8912), Documents (:8913), Code sandbox (:8914), Whisper (:8915), TTS (:8916), Security (:8919), Memory (:8920), RAG (:8921), Research (:8922), Browser (:8923), CAD render (:8926), Proxmox (:8927) | (internal) |
| Pipeline MCP | Stack introspection + FastContext code explorer for Claude Code / opencode | :8928 (host-native) |
| MITRE ATT&CK MCP | Technique lookup, data sources, detections — deterministic, not RAG | :8929 (internal) |
| Detections MCP | SPL library search, validate_syntax, explain_detection | :8932 (internal) |
| Wiki MCP | Canonical knowledge layer — search, get_unit, explain, cited answers | :8931 (internal) |
| MLX Transcribe | Diarized transcription — mlx-whisper + pyannote (Apple Silicon) | :8924 (host-native) |
| MLX Speech | Kokoro TTS + Qwen3-TTS/ASR (Apple Silicon) | :8918 (host-native) |
| Embedding | Harrier-0.6B text embeddings for RAG | :8917 (host-native) |
| Reranker | Qwen3-Reranker-0.6B two-stage RAG | :8925 (host-native) |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

---
