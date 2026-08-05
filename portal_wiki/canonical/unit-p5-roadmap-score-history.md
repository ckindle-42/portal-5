---
id: unit-p5-roadmap-score-history
kind: what
title: "P5_ROADMAP \u2014 Score History"
sources:
- type: code
  path: portal/platform/inference/notifications/channels/webhook.py
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py
- type: code
  path: CHANGELOG.md
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.593756
updated_at: 1784946220.593756
---

The roadmap score-history records which P5-FUT items shipped, and each shipped
item is verifiable in current code. P5-FUT-004 (webhook notifications) is
implemented in `portal/platform/inference/notifications/channels/webhook.py`.
P5-FUT-005 (weighted keyword routing) is Layer 2 auto-routing — the
`_detect_workspace()` function in `portal/platform/inference/router/routing.py`.
P5-FUT-006 (LLM-based intent routing) is Layer 1 — `_route_with_llm()` in the
same module. P5-FUT-009 (model-size-aware admission control) shipped in the
now-retired MLX proxy and survives only in
`scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py`. The completion scores
themselves are dated snapshots recorded in `CHANGELOG.md` at each milestone;
current code is the live status, not the historical score.

## Why

A percentage from a past date cannot be re-derived from current code and would go
stale the moment anything changes, so the unit drops the historical figures. What
stays true is the mapping of each shipped roadmap item to its implementation, and
that mapping is asserted here with file paths so the unit remains verifiable
against the live tree rather than against a snapshot.
