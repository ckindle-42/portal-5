---
id: unit-known-limitations-omlx-balanced-ceiling
kind: what
title: oMLX Balanced Ceiling Moves With Host Free Memory
sources:
- type: code
  path: portal/platform/inference/load_guard.py
- type: code
  path: scripts/omlx_memory_tier.py
claims: []
confidence: high
tags:
- known-limitations
- omlx
- memory
created_at: 1792627200
updated_at: 1792627200
---

#### oMLX balanced memory-guard ceiling moves with free memory (2026-10-22)

- **ID**: P5-OMLX-CEILING-001
- **Status**: OPEN. Observed 2026-10-22 on oMLX 0.7.2 with `memory_guard_tier` `balanced` in the host oMLX settings.
- **Description**: oMLX's `final_ceiling` under the balanced tier moves with host free memory. Across one night it ranged from 18 GB to 42 GB. The load guard takes headroom as that ceiling minus oMLX's residents, plus idle Ollama residents, minus the margin. The same large Ollama load can fit or be refused as the ceiling moves, with no change in this repo.
- **Mitigation**: The guard already reads the ceiling at admission time. A fit recorded earlier in the night is stale. Live measurements of large Ollama loads need a quiet host so other work is not also pushing the ceiling around. The balanced ceiling is not a fixed budget.

#### Why

The guard uses oMLX's ceiling as the host oracle because Ollama's own resident sizes under-report what a runner holds. That oracle is only as stable as the tier that computes it. Balanced follows free memory, so other loads, cache, and parallel test workers move the number the guard subtracts from. An admission or a refusal then describes the host at that moment, not a property of the model.
