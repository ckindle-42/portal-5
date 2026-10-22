---
id: unit-known-limitations-load-guard-omlx-swap
kind: what
title: Load Guard Refused During an oMLX Model Swap
sources:
- type: code
  path: portal/platform/inference/load_guard.py
- type: code
  path: tests/unit/test_load_guard.py
claims: []
confidence: high
tags:
- known-limitations
- omlx
- memory
created_at: 1792627200
updated_at: 1792627200
---

#### Load guard refused during an oMLX model swap (2026-10-22)

- **ID**: P5-LOADGUARD-SWAP-001
- **Status**: OPEN. A reported load is waited out. oMLX still exposes no unload signal.
- **Description**: On 2026-10-22 the load guard refused an Ollama cold load at once, with the reason "nothing in flight to wait for", while oMLX was mid-swap. A swap is not an in-flight pipeline request and not an idle resident the guard can free, so the quiet path treated the host as settled and returned HTTP 507 without waiting.
- **First fix**: `1a32e66f` merges `9ff0deeb` (wait during engine model swaps). Admission waits while oMLX reports `is_loading` or `models_loading`, and keeps refusing at once only when those surfaces are clear and nothing is in flight.
- **Rework**: `plan/guard-race` continues that wait so a transition the guard can see is not classified as quiet.
- **Counter round**: round 6 (commit a73c88dc) makes oMLX's memory counter act as the unload signal the status surfaces lack: admission snapshots `current_model_memory` before posting an unload, treats a queued (202) unload as settled on any counter drop, and re-measures instead of refusing quiet when the counter drops between passes or on the quiet path's own re-measure.
- **Round 9 (2026-10-22 UAT `auto-coding::fast-repair`)**: the guard had already unloaded the idle oMLX seat (202 at 08:18:58.9, unloaded 08:19:02.4, 16.00 GB freed); the refusal's `oMLX headroom 19.8` was the whole host-derived ceiling with nothing resident. The only reclaimable memory was an idle Ollama resident, which admission unloaded and then wrote off as soon as `/api/ps` dropped it, refusing quiet ~0.2 s later against the pre-free ceiling. A free now stays pending until the measured headroom rises above its value at the free, bounded by `_FREE_SETTLE_S` (5 s) so a free that moves nothing still refuses.
- **Remaining gap**: oMLX still exposes no unload field. A swap whose unload has not yet moved the counter when the guard re-measures still looks like a settled host, and admission can refuse at once; an observed drop buys one re-measure, so an unload that lands later still races the deadline.

#### Why

The quiet path exists so a load that cannot fit, and that nothing currently running will free, fails immediately instead of sitting out the deadline. That is the right call when oMLX's memory is stable. The status surfaces the guard reads name loads and active requests; they do not name an unload, so the guard reads the counter's direction instead — a falling counter keeps admission waiting, and only a counter stable across a re-measure counts as settled. A swap whose unload has not moved the counter yet can still be refused as if the machine were settled.
