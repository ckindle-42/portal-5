---
id: unit-fish-speech-setup-testing
kind: what
title: Testing the TTS backend
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5413098
updated_at: 1784946220.5413098
---

Two probes exercise the speech stack without loading a model. First,
`curl http://localhost:8916/health` hits the TTS MCP health route, which reports
the active backend (`kokoro` or `fish_speech`) and whether voice cloning is
available; `docker-compose.yml` runs the same request as the container
healthcheck. Second, `./launch.sh logs mcp-tts` streams the service log so a
startup failure or a model download stall is visible. A full end-to-end check
calls the `speak` tool with a short text and a known voice ID, then verifies the
response carries a `download_url`. These are the checks the deployment itself
relies on, and they run entirely against the live service.

## Why

Testing guidance must name commands that exist, and the previous section was an
empty code fence that told an operator nothing. The health route, the compose
healthcheck and the logs subcommand are the verification points the platform
already depends on, so documenting them means the operator's checks and the
system's own health probes agree rather than contradict each other.
