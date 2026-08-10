---
id: unit-known-limitations-devstral-2509-upgrade-blocked-model-not-published
kind: what
title: "KNOWN_LIMITATIONS \u2014 Devstral 2509 Upgrade Blocked \u2014 Model Not Published"
sources:
- type: code
  path: config/personas/bench_devstral.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6619809
updated_at: 1784946220.6619809
---

- **ID**: P5-BENCH-DEVSTRAL-2509
- **Description**: A Devstral 2509 upgrade is blocked because no such model is registered in the catalog. The bench persona `config/personas/bench_devstral.yaml` is named for the 2507 (July 2025) variant, and both `bench-devstral` and `bench-devstral-small-2` in `config/portal.yaml` pin to `devstral:24b` and `devstral-small-2:latest` respectively — neither `config/backends.yaml` nor the workspaces reference any 2509 tag.
- **Operator action**: Re-run the persona-intent verification when a 2509 model card appears and is registered as a catalog candidate; the MLX-tagged variant named in the original finding is no longer relevant because the MLX inference tier is retired.

## Why

The bench workspaces must not silently promote to a model that was never verified, so the catalog is the gate: a 2509 tag cannot be routed until it exists as a backend model entry and the bench persona is updated to name it. Recording the blocked upgrade preserves the intent while making the blocker mechanical — a missing catalog registration — rather than a stale prose promise.
