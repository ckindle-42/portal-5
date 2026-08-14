---
id: unit-fish-speech-setup-start-api-server-on-port-5005
kind: what
title: "TTS server port \u2014 8916, not 5005"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.539288
updated_at: 1784946220.539288
---

The claim that Fish Speech listens on port 5005 is false for this repository. The
only speech endpoint the TTS MCP exposes is the MCP itself, which binds
`TTS_MCP_PORT` with a default of 8916, as shown in `docker-compose.yml` and the
variable read inside `tts_mcp.py`. The upstream `tools.api` server command
belongs to the Fish Speech source tree that Portal 5 does not run; the MCP loads
`Text2Speech` directly in-process. A working TTS stack therefore answers on 8916,
and the container healthcheck probes that same port via the health route.

## Why

A port that nothing listens on is a debugging trap, and the old guide set one up
at 5005 while the MCP served 8916. Pinning the port to the environment variable
that actually controls it makes the unit a reliable map from the compose file to
the running process, so an operator can predict exactly where to send a request.
