---
id: unit-comfyui-setup-start
kind: what
title: "COMFYUI_SETUP \u2014 Start"
sources:
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.559121
updated_at: 1784946220.559121
---

Starting the engine manually runs `~/ComfyUI/start.sh`. That generated script
resolves its own directory, changes into it, and executes the virtualenv Python
against the main entrypoint with a listen flag bound to all interfaces and the
fixed port. The same arguments are baked into the launchd plist, so the manual
script and the auto-start agent run identical invocations. After start, the
bridge MCP can reach the engine at the loopback address.

## Why

A generated start script exists so the manual and agent-managed paths invoke the
engine identically; duplicating the command by hand invites drift between what an
operator runs in a terminal and what the agent runs at login. Binding all
interfaces lets the Docker bridge reach the host engine over the shared network.
