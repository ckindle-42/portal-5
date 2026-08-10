---
id: unit-comfyui-setup-stop
kind: what
title: "COMFYUI_SETUP \u2014 Stop"
sources:
- type: code
  path: scripts/lib/services.sh
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.559435
updated_at: 1784946220.559435
---

Stopping the engine uses the launchctl agent label. Because the plist declares
KeepAlive, a stop only halts the current process and the agent may relaunch it
shortly after; keeping the engine down requires unloading the agent entirely.
Logs are written to the files configured in the plist, so inspecting them is the
diagnostic step before deciding whether a stop is clean. On the Docker fallback
path the equivalent is stopping the compose service instead.

## Why

The KeepAlive flag makes plain stop transient by design, so the unit has to
distinguish a momentary stop from a persistent shutdown to avoid confusing
operators. Documenting the unload form prevents a false "it won't stay stopped"
conclusion, and the log paths give the follow-up diagnostic.
