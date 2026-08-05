---
id: unit-model-catalog-qwen3-6-27b-oq8-mtp
kind: what
title: "MODEL_CATALOG \u2014 `Qwen3.6-27B-oQ8-mtp`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 778def71961fd1bb2f1088be9754388706facf7a
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

`Qwen3.6-27B-oQ8-mtp` is the oQ-quantized Qwen3.6-27B with a merged Lightning MTP head (built during the 2026-05-28 re-eval), served by the oMLX evaluation backend. `config/backends.yaml` registers it in the `omlx` group's `omlx-local` backend with `supports_tools: false`. Phase-0 Gate-2b with the toggle verified against the server log measured MTP off 8.1-8.4 t/s versus on 18.0-20.5 t/s — a 2.22-2.47x speedup at 82-95% draft acceptance. It is the reference artifact for Phase-4 MTP enablement on coding and security primaries, and no `config/portal.yaml` workspace consumes it.

## Why

Grounding anchors the model to the single `omlx-local` registration whose supports_tools false flag reflects its eval-only role, and records that no portal.yaml workspace references it. The MTP speedup figures are kept as the institutional evidence behind the Phase-4 plan — they are a measured probe result, not a config-derived claim, so they are stated as measurements.
