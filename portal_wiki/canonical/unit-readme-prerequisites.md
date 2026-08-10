---
id: unit-readme-prerequisites
kind: what
title: "README \u2014 Prerequisites"
sources:
- type: code
  path: scripts/lib/util.sh
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6780841
updated_at: 1784946220.6780841
---

The requirements `./launch.sh up` actually enforces are in `_check_hardware` in
`scripts/lib/util.sh`, run on every start:

| Requirement | Enforced minimum | Notes |
|---|---|---|
| **RAM** | 16 GB | warns below 32 GB (enough for core models; 32+ for the full catalog) |
| **Disk** | 20 GB free | warns below 50 GB; FLUX alone is about 12 GB |
| **Docker** | running daemon (5 s timeout) | a hung Docker Desktop is detected and the user is offered a process kill |
| **Ollama** | reachable on :11434 | auto-restarted by `_ensure_native_services` via `sudo -n launchctl kickstart -k system/com.portal5.ollama` if configured |

Apple Silicon is the recommended platform: `install-ollama` reports the pinned
native Ollama install's status (a system LaunchDaemon, `com.portal5.ollama` —
not Homebrew, which lags upstream releases below this project's minimum
version; disabled and uninstalled 2026-08-10), `install-comfyui` sets up
ComfyUI with an MPS venv, and the native MLX services run on the M-series
Metal path. On non-Apple-Silicon machines the installers print Linux/Docker
alternatives instead of failing.

## Why

The hardware gate runs before any pull or compose step so the stack fails fast
with a readable reason instead of dying mid-download or silently OOMing at first
inference. The thresholds come from the real working set: the router plus a pinned
model need 16 GB, and the FLUX checkpoint sets the floor for the disk check.
