---
id: unit-ADMIN_GUIDE-ollama-max-loaded-models-3
kind: why
title: "ADMIN_GUIDE \u2014 OLLAMA_MAX_LOADED_MODELS (now 5, was 3)"
sources:
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: portal/modules/security/core/commands/run.py
- type: code
  path: portal/platform/inference/router/routing.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.815617
updated_at: 1783195000.815617
---

The slot count is `OLLAMA_MAX_LOADED_MODELS`: `.env.example` ships 5 (router model plus four inference models for chained and parallel bench work), while the compose `docker-ollama` profile still defaults to 3. The number must cover the router plus every concurrently-resident inference model — a multi-hop security chain needs each hop's model hot, or Ollama evicts and cold-reloads between hops. `run.py` reads the live value and emits a preflight warning when `--parallel-workspaces` is used with a count too low for the chain, and routing.py's header records the router model's own slot requirement. After changing it, verify the running server picked up the new value rather than assuming.

## Why

The slot count is a memory-versus-availability trade, not a throughput knob: each resident slot competes for unified memory, but a count below the chain length converts multi-hop workspaces into cold-load stalls. The 3-to-5 bump exists so the security bench can keep four distinct chain models resident during parallel dispatch.
