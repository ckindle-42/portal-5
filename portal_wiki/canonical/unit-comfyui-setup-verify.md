---
id: unit-comfyui-setup-verify
kind: what
title: "COMFYUI_SETUP \u2014 Verify"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.561763
updated_at: 1784946220.561763
---

Verification is a single request to the engine's system statistics endpoint.
Because the engine is host-native, hitting the loopback port from the host
confirms both that the process is up and that it answers the same health URL the
compose definition polls in its health check. A JSON document in the response
with device and memory fields indicates the engine is ready; a connection
refusal means the launchd agent is not running, and the log files are the next
place to look.

## Why

The verification command is the same endpoint the container health check probes,
which keeps the operator's manual check and the stack's automated check in
agreement about what healthy means. That symmetry avoids the classic case where a
service passes its health check but the human verification URL differs.
