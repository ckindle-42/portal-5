---
id: unit-readme-what-starts-automatically
kind: what
title: "README \u2014 What Starts Automatically"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: config/portal.yaml
- type: code
  path: scripts/lib/util.sh
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.678988
updated_at: 1784946220.678988
---

`./launch.sh up` starts the core Docker stack (compose services plus profiles
auto-selected from Telegram/Slack tokens). Host-native Apple Silicon services
start when their launchd agent has been installed — `_ensure_native_services` in
`scripts/lib/util.sh` checks each registered launchd label (ComfyUI, Music MCP,
MLX Speech, MLX Transcribe, embedding) and boots the service via `launchctl` or a
background `nohup` fallback.

| Service | What it does | URL/port |
|---|---|---|
| Open WebUI | Chat interface — main portal | http://localhost:8080 |
| Portal Pipeline | Routing, auth, metrics, MCP dispatch | :9099 |
| Ollama | Local GGUF models via Metal | :11434 |
| SearXNG | Private web search | :8088 |
| ComfyUI | Image generation (host-native; video shelved) | http://localhost:8188 |
| MCP fleet | ComfyUI :8910, Music :8912, Documents :8913, Sandbox :8914, Whisper :8915, TTS :8916, Security :8919, Memory :8920, RAG :8921, Research :8922, Browser :8923, CAD :8926, Proxmox :8927 | config/portal.yaml |
| Pipeline MCP | Stack introspection + FastContext explorer | :8928 |
| MITRE ATT&CK MCP | Technique lookup, data sources, detections | :8929 |
| Detections MCP | SPL library search, validate_syntax, explain | :8932 |
| Wiki MCP | Canonical knowledge layer — search, get_unit | :8931 |
| MLX Transcribe | Diarized transcription (Apple Silicon) | :8924 |
| MLX Speech | Kokoro TTS + Qwen3-TTS/ASR (Apple Silicon) | :8918 |
| Embedding | Harrier-0.6B text embeddings | :8917 |
| Reranker | Qwen3-Reranker-0.6B two-stage RAG | :8925 |
| Prometheus | Metrics collection | http://localhost:9090 |
| Grafana | Metrics dashboard | http://localhost:3000 |

The MCP fleet and its ports are defined in `config/portal.yaml` (`mcp_fleet:`);
the compose container names and health checks are in
`deploy/portal-5/docker-compose.yml`.

## Why

The split into a compose stack and host-native launchers exists because Apple
Silicon runtimes (MLX, ComfyUI, embeddings) are faster and lighter outside Docker,
while the web services benefit from compose's networking, health checks and
restart policy. launchd registration makes the native services survive reboots and
crashes, so `up` only needs to confirm or start them rather than install them.
