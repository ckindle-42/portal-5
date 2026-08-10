---
id: unit-readme-wait-for-ollama-to-finish-loading-then-try-again
kind: what
title: "README \u2014 Wait for Ollama to finish loading, then try again"
sources:
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.688859
updated_at: 1784946220.688859
---

"Wait for Ollama to finish loading, then try again" is the guidance for a cold
start. During `up`, `_ensure_native_services` (`scripts/lib/util.sh`) restarts
Ollama via `sudo -n launchctl kickstart -k system/com.portal5.ollama` on Apple
Silicon (the pinned native install, `com.portal5.ollama` — not Homebrew, which
was uninstalled 2026-08-10) when it is configured but not responding, or via
`nohup ollama serve` on Linux, then polls `http://localhost:11434/api/tags` up
to 10 seconds before reporting success or warning. The router only sees healthy
backends once models finish loading, so an immediate request right after boot
can hit an empty backend list — retrying after Ollama responds is the intended
fix.

**First run taking too long:** the FLUX.1-schnell checkpoint is about 12 GB, so on
a slower connection the download dominates boot time; the `hf download` based
pull commands resume interrupted transfers.

**Port already in use:** find the owner with `lsof -i :8080` — the same tool
`_check_ports` uses to print the conflicting PID and its `kill` hint when `up`
aborts.

## Why

Ollama loads models lazily and the checkpoint downloads are large, so "wait and
retry" is not a workaround but the documented behavior of the loader: the stack
can be up before every model is resident. The 10-second readiness poll in
`_ensure_native_services` draws the line between a service that is starting and
one that is actually broken.
