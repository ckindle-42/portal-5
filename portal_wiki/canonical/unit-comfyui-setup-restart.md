---
id: unit-comfyui-setup-restart
kind: what
title: "COMFYUI_SETUP \u2014 Restart"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: portal/modules/media/tools/_admission.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.559772
updated_at: 1784946220.559772
---

The restart idiom is the launchd agent: stop the agent then start it again, both
under the registered label. The admission module's refusal message uses the more
aggressive kickstart form with the kill flag when it wants to force a full
restart after unloading a heavy model. Restarting matters operationally because
the engine's single long-running MPS process does not reliably evict one model
family's weights when another loads, so a restart is the practical way to clear
resident memory between different model families — the same reason the memory
admission gate exists.

## Why

Restart is the memory-eviction mechanism for a process that cannot reliably
release a previous model family's weights on MPS. The admission gate blocks
oversized jobs pre-flight, but between-family switching still requires an actual
process restart, which is why the refusal message and the documentation both
route operators to the launchd restart command.
