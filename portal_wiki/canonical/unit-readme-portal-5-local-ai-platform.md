---
id: unit-readme-portal-5-local-ai-platform
kind: what
title: "README \u2014 Portal 5 \u2014 Local AI Platform"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: .env.example
- type: code
  path: KNOWN_LIMITATIONS.md
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.67769
updated_at: 1784946220.67769
---

Portal 5 is a complete, private AI platform that runs on your hardware: text,
code, security analysis, images, music, documents and voice — all local. It
connects to Open WebUI, Telegram and Slack, and routes each task automatically to
the workspace that carries the right model and toolset. Image and video
generation are MLX-native on Apple Silicon (MFLUX for images; `ltx-2-mlx` for
video, behind the `video` module — off by default, shipped enabled).

Inference is fully local: prompts and responses never leave the machine. Model
downloads from HuggingFace or Ollama registries transmit standard HTTP metadata,
and if `HF_TOKEN` is configured for gated models, authentication requests are sent
to HuggingFace. No cloud accounts or usage fees are required.

## Why

The platform is scoped as an enhancement layer over Open WebUI rather than a
replacement web stack, which keeps authentication, chat history and RAG inside a
battle-tested frontend while the pipeline owns routing and model selection. Image
and video generation moved to the host MLX layer (from a ComfyUI path that Metal's
lack of FP8 made unrunnable here); video is an M7 module that is disabled by
default but shipped enabled, so flipping it is a one-command toggle rather than
a rebuild.
