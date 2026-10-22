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
updated_at: 1792684036
---

#### oMLX balanced memory-guard ceiling moves with free memory (2026-10-22)

- **ID**: P5-OMLX-CEILING-001
- **Status**: MITIGATED 2026-10-22. A fixed budget is available on both sides and neither is applied on this host: `LOAD_GUARD_CEILING_GB` in the Pipeline (unset budgets against the live ceiling), and oMLX's `custom` tier with `memory.memory_guard_custom_ceiling_gb` (host still runs `balanced`). The record is `coding_task/REPORT_OMLX_CEILING.md`.
- **Description**: oMLX's `final_ceiling` under the balanced tier moves with host free memory. Across one night it ranged from 18 GB to 42 GB. The load guard takes headroom as that ceiling minus oMLX's residents, plus idle Ollama residents, minus the margin. The same large Ollama load can fit or be refused as the ceiling moves, with no change in this repo.
- **Mitigation**: The guard budgets against `LOAD_GUARD_CEILING_GB` when it is set — a fixed cap on model memory (oMLX residents plus idle Ollama residents), so a given load gets the same verdict while the ceiling moves — and against oMLX's live `final_ceiling` when it is not. The cap covers Ollama admission only: oMLX's own guard never sees it, so a value above oMLX's normal ceiling lets oMLX fill the budget alone and the guard then refuses Ollama loads until an oMLX model is freed. oMLX's fixed figures cannot be substituted directly: the tier's static ceiling and physical total are maxima, and on 2026-10-22 balanced's `static_ceiling` (58.88 GiB) exceeded the live ceiling (40.21 GiB) by the 18.67 GiB of memory other processes held, so budgeting against it would readmit the 2026-10-07 load shape. The host-side equivalent is `memory_guard_tier: custom` with `memory.memory_guard_custom_ceiling_gb` pinned (40 GiB reproduces the quiet-host ceiling); `./launch.sh up` rewrites the tier to balanced (`launch.sh:54`) and `scripts/omlx_memory_tier.py` cannot set `custom`, so applying it is an operator decision. Live measurements of large Ollama loads still need a quiet host, and a fit recorded earlier in the night is stale while no fixed budget is set.
- **Watching the movement (2026-10-22)**: the headroom the guard decided on and oMLX's live `final_ceiling` at that decision are now gauges — `portal5_load_guard_headroom_bytes` and `portal5_load_guard_ceiling_bytes`, last-decision values across Pipeline workers — charted on the Model Management dashboard (`config/grafana/dashboards/portal5_model_management.json`), so the ceiling's drift through the night is visible without a log dive. With a fixed `LOAD_GUARD_CEILING_GB` the headroom gauge stops moving with free memory while the ceiling gauge keeps recording oMLX's live figure; without one, both move together, and a refusal is judged against the headroom the gauge shows at that moment.

#### Why

The guard uses oMLX's ceiling as the host oracle because Ollama's own resident sizes under-report what a runner holds. That oracle is only as stable as the tier that computes it. Balanced follows free memory, so other loads, cache, and parallel test workers move the number the guard subtracts from. An admission or a refusal then describes the host at that moment, not a property of the model. A fixed budget makes the verdict a property of the model set again, at the cost of fixing the reserve for everything else — which is why the number is an operator decision, not a constant this repo can derive.
