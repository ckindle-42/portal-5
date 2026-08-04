---
id: unit-fish-speech-setup-create-virtual-environment
kind: what
title: "No virtual environment \u2014 the mcp-tts container is the runtime"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: Dockerfile.mcp
- type: code
  path: portal/modules/media/tools/tts_mcp.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.537683
updated_at: 1784946220.537683
---

Portal 5 never creates a Python virtual environment for speech, because the
`mcp-tts` Docker container is the runtime. `docker-compose.yml` launches it with
`python -m portal.modules.media.tools.tts_mcp` and `Dockerfile.mcp` pins the
speech dependencies such as `kokoro-onnx`, `soundfile` and `numpy` into the image
at build time, so there is no virtualenv to activate before synthesis.
`tts_mcp.py` reads its configuration like `TTS_BACKEND`, `TTS_DEFAULT_VOICE` and
`TTS_MCP_PORT` from container environment variables supplied by the compose file,
which is the only environment the server ever sees.

## Why

The older guide assumed a host virtualenv because it described a manual Fish
Speech install that predates the containerised MCP. Writing the unit around the
container-as-environment model prevents operators from hunting for a virtualenv
that does not exist and makes the compose file the single source of truth for the
speech server's settings.
