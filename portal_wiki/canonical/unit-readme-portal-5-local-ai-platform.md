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
last_generated_commit: 956ee226e319e701e3605c9de6950bfa437a56f0
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
the workspace that carries the right model and toolset. The retained
video-generation code is shelved and not part of normal operation, documented in
`KNOWN_LIMITATIONS.md` and left unregistered in `config/portal.yaml`
(`mcp_fleet`), where the `video` fleet entry is intentionally removed.

Inference is fully local: prompts and responses never leave the machine. Model
downloads from HuggingFace or Ollama registries transmit standard HTTP metadata,
and if `HF_TOKEN` is configured for gated models, authentication requests are sent
to HuggingFace. No cloud accounts or usage fees are required.

## Why

The platform is scoped as an enhancement layer over Open WebUI rather than a
replacement web stack, which keeps authentication, chat history and RAG inside a
battle-tested frontend while the pipeline owns routing and model selection. The
video shelving is an honesty contract: code is retained for future work but is
neither advertised nor operated until the crash limitations are resolved.
