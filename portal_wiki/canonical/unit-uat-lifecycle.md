---
id: unit-uat-lifecycle
kind: mixed
title: "UAT lifecycle \u2014 unload/pre-warm/ComfyUI start-stop"
sources:
- type: code
  path: tests/uat/lifecycle.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799280.253008
updated_at: 1785799280.253008
---

Model unload, pipeline pre-warm, and ComfyUI start/stop for the UAT driver.

## Why

The run lifecycle (evict inference models to free memory, pre-warm the pipeline, start and stop ComfyUI for the image sections) is the sequencing that makes a UAT run repeatable. The import-direction note (lifecycle imports `memory_pct` directly from tests.memory_guard, not via tests.uat.health) is the cycle break that keeps the module graph acyclic — health imports unload from here, so lifecycle must not import health back.

## Interfaces

The unload, pre-warm, and ComfyUI lifecycle functions.

## Gotchas

The import direction is a deliberate cycle break — adding a lifecycle-to-health import would re-introduce the cycle the extraction removed.
