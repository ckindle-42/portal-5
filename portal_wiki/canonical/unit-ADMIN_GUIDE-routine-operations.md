---
id: unit-ADMIN_GUIDE-routine-operations
kind: why
title: "ADMIN_GUIDE \u2014 Routine Operations"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8131342
updated_at: 1783195000.8131342
---

Routine lifecycle is one command per operation. `./launch.sh status` runs `_cmd_status` in scripts/lib/util.sh — a per-service health table covering the Docker stack, native services, and the pipeline's `backends_healthy` counts. `./launch.sh logs` tails the portal-pipeline container by default; the default stack has no Ollama container (the compose `ollama` service sits behind the `docker-ollama` profile), so native Ollama logs come from `/opt/homebrew/var/log/ollama.log` (the `com.portal5.ollama` LaunchDaemon's configured log path, despite the `homebrew` directory prefix — not Homebrew-managed) or `~/.portal5/logs/ollama.log` on Linux, not from `logs ollama`. `./launch.sh seed` re-runs `openwebui-init` idempotently, `./launch.sh down` stops the stack via `_do_down` with data preserved, and `./launch.sh clean` removes only the `portal-5_open-webui-data` volume, keeping Ollama models.

## Why

Each verb carries an explicit data story — `down` preserves, `clean` wipes only Open WebUI data, `clean-all` wipes models — so an operator never reaches for `docker compose down -v` and accidentally deletes model weights. `logs` defaulting to the pipeline matches where the interesting decisions are logged.
