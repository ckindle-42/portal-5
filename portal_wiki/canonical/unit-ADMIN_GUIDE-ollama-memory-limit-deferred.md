---
id: unit-ADMIN_GUIDE-ollama-memory-limit-deferred
kind: why
title: "ADMIN_GUIDE \u2014 OLLAMA_MEMORY_LIMIT (deferred)"
sources:
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.817065
updated_at: 1783195000.817065
---

Native Ollama runs with no memory cap by default. `OLLAMA_MEMORY_LIMIT=0` in `.env.example` means "unlimited", and in the compose `docker-ollama` profile the value becomes the container's `deploy.resources.limits.memory`; a native install ignores it entirely, so the plist is the only lever there. Ollama handles memory pressure by offloading layers to CPU rather than crashing. If Metal OOM errors or kernel panics appear under heavy multi-model load, the escalation path is an `OLLAMA_MEMORY_LIMIT` entry in the launchd plist's `EnvironmentVariables` block (reloaded via `launchctl`), or trimming `OLLAMA_MAX_LOADED_MODELS` instead of adding a cap.

## Why

The absent cap is a deliberate default, not an oversight — the reference slot/memory mix fits the target hardware, so a hard limit would only add an artificial ceiling. Capping is reserved as the escalation move for actual OOM symptoms, which keeps the common case simpler and leaves the tuning lever available when it is genuinely needed.
