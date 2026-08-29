---
id: unit-uat-lifecycle
kind: mixed
title: "UAT lifecycle — model unload / pipeline pre-warm"
sources:
- type: code
  path: tests/uat/lifecycle.py
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799280.253008
updated_at: 1785799280.253008
---

Model unload, pipeline pre-warm, and media-MCP health for the UAT driver.

## Why

The run lifecycle (evict inference models to free memory, pre-warm the pipeline) is the sequencing that makes a UAT run repeatable. The MLX image/video generation MCPs are launchd-supervised and release memory between jobs, so the driver no longer starts/stops a generation engine per phase — it only probes health (`_mflux_running`). The import-direction note (lifecycle imports `memory_pct` directly from tests.memory_guard, not via tests.uat.health) is the cycle break that keeps the module graph acyclic — health imports unload from here, so lifecycle must not import health back.

## Interfaces

The unload, pre-warm, and `_mflux_running` health-probe functions.

## Gotchas

The import direction is a deliberate cycle break — adding a lifecycle-to-health import would re-introduce the cycle the extraction removed.
