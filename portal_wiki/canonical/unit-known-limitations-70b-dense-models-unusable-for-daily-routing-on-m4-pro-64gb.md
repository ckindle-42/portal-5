---
id: unit-known-limitations-70b-dense-models-unusable-for-daily-routing-on-m4-pro-64gb
kind: what
title: "KNOWN_LIMITATIONS \u2014 70B Dense Models Unusable for Daily Routing on M4\
  \ Pro 64GB"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: tests/unit/test_pipeline.py
last_generated_commit: 63cbca4c591d2d00f1cc9e3101ffa91f84a9a4a0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.673774
updated_at: 1784946220.673774
---

- **ID**: P5-SPEED-001
- **Description**: Dense 70B-class models are unusable for daily routing on this M4 Pro 64GB host. The catalog removal record in `tests/unit/test_pipeline.py` documents measured 3.8 TPS for `llama3.3:70b-q4_k_m`, below the project's 20 TPS interactive floor, with `supports_tools: false`, bench-only. Both `llama3.3:70b-q4_k_m` and `dolphin-llama3:70b-q4_k_m` survive only as `retired: true` entries in the `config/portal.yaml` pull registry, excluded from default pulls. An MLX 3-bit ~28GB variant was theorized but never validated, and the MLX inference tier itself is retired.
- **Mitigation**: No 70B dense model is registered in any `config/backends.yaml` backend group for daily routing. Daily-routed workspaces use the compact catalog; 70B variants exist only as retired registry history.

## Why

The 64GB unified-memory budget and a 20 TPS interactive-latency floor combine to exclude dense 70B models from the routing catalog: their measured throughput sits at roughly a fifth of the floor at any quality-preserving quantization, and their weight footprints would crowd out the co-resident router and inference peers scheduling depends on. Keeping them as retired registry entries preserves the measured evidence so a cluster-scale node, not a catalog edit, is the only route back in.
