---
id: unit-model-catalog-qwen3-6-27b-oq8-mtp
kind: what
title: "MODEL_CATALOG — `Qwen3.6-27B-oQ8-mtp`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 29bdbca4
  section: '`Qwen3.6-27B-oQ8-mtp`'
last_generated_commit: 29bdbca4
confidence: high
tags:
- docs
created_at: 1785716664.2314298
updated_at: 1785716664.2314298
---

oQ-quantized Qwen3.6-27B with a merged Lightning MTP head (built during the 2026-05-28 re-eval), served by the oMLX evaluation backend. Phase-0 Gate-2b with toggle verified against the server log: MTP off 8.1-8.4 t/s, on 18.0-20.5 t/s = 2.22-2.47x speedup at 82-95% draft acceptance. Reference artifact for Phase-4 MTP enablement on coding/security primaries.
