---
id: unit-readme-architecture
kind: what
title: "README \u2014 Architecture"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: config/portal.yaml
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: scripts/embedding-server.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6922922
updated_at: 1784946220.6922922
---

The deployment is a Docker compose stack plus host-native runtimes, orchestrated
by `launch.sh`. Open WebUI (port 8080) is the user-facing chat surface and the
only component a human normally opens. It talks to the Portal Pipeline (port
9099), which performs routing, `PIPELINE_API_KEY` authentication, metrics
collection and MCP tool dispatch. The pipeline is the OpenAI-API-compatible
endpoint registered in Open WebUI; it is stateless for conversation routing and
forwards to Ollama (port 11434), the single inference tier, which runs GGUF
models through its Metal backend on Apple Silicon.

```
┌──────────────┐        ┌──────────────────────────┐
│  Open WebUI  │ ─────► │  Portal Pipeline :9099   │
│     :8080    │        │  routing / auth / MCP    │
└──────────────┘        └──────┬───────┬───────────┘
                               │       │
                        ┌──────▼──┐ ┌──▼───────────────┐
                        │ Ollama  │ │ MCP fleet        │
                        │ :11434  │ │ :8910–:8932      │
                        └─────────┘ └──────────────────┘
Telegram Bot ──► Pipeline    Slack Bot ──► Pipeline
(profile telegram)           (profile slack)
Grafana :3000 ◄── Prometheus :9090 ◄── /metrics
```

The MCP fleet, defined in the `mcp_fleet:` block of `config/portal.yaml`, exposes
tool servers for documents, code sandboxing, TTS, research, memory, RAG, browser
automation, CAD, Proxmox and the canonical wiki. Host-native MLX runtimes serve
speech (`scripts/mlx-speech.py`, port 8918), diarized transcription
(`scripts/mlx-transcribe.py`, port 8924), embeddings
(`scripts/embedding-server.py`, port 8917) and retrieval reranking (port 8925).
Chat inference is Ollama-only: the MLX inference proxy that once listened on
ports 8081/18081/18082 was retired in commit 3a0c58e.

## Why

Keeping a single inference tier on Ollama avoids running a second model-serving
stack against the same GPU memory; MLX survives only where Ollama has no
equivalent runtime — audio synthesis, diarization, embeddings and reranking. One
tier also means one model catalog (`config/backends.yaml`) and one pull path for
operators, which is why the retained MLX runtimes are explicitly non-chat.
