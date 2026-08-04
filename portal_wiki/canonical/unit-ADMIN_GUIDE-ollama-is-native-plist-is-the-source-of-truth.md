---
id: unit-ADMIN_GUIDE-ollama-is-native-plist-is-the-source-of-truth
kind: why
title: "ADMIN_GUIDE \u2014 Ollama is Native \u2014 Plist Is the Source of Truth"
sources:
- type: code
  path: scripts/lib/services.sh
- type: code
  path: scripts/lib/util.sh
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.816087
updated_at: 1783195000.816087
---

On Apple Silicon the default Ollama is native under Homebrew launchd, not a container. `_launch_install_ollama` in scripts/lib/services.sh installs via `brew install ollama` and starts it with `brew services start ollama`; `_ensure_native_services` in scripts/lib/util.sh auto-starts it whenever `up` finds it installed but not responding. The compose `ollama` service is gated behind the `docker-ollama` profile, so compose env vars (e.g. `OLLAMA_MAX_LOADED_MODELS`) do not reach a native server. The authoritative config for native is the launchd plist:

```
~/Library/LaunchAgents/homebrew.mxcl.ollama.plist
```

Edit it and reload via `launchctl`; relocating `OLLAMA_MODELS` likewise needs `brew services restart ollama`.

## Why

Native and container Ollama are two separate config surfaces, and the compose file documents only the container one. An operator who tunes the container's env block while running native (the default) has made a change that never takes effect — the plist is the only lever that does, so the source of truth must be stated explicitly.
