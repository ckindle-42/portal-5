---
id: unit-archive-mlx-watchdog
kind: mixed
title: "MLX watchdog \u2014 archived external supervisor"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-watchdog.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797154.218142
updated_at: 1785797154.218142
---

This is the MLX watchdog v2 — an async, memory-aware monitor for the retired
MLX subsystem. It recovered from two failure modes the in-proxy recovery
could not: a full proxy crash (only an external daemon can restart the proxy
itself) and zombie servers accumulating while the proxy was alive but stuck
(event-loop blocked or stalled on a long sync call).

## Why

The watchdog encoded the operational lesson that a service cannot reliably
recover its own supervisor: the proxy's zombie cleanup only ran when the
proxy was healthy, so a wedged proxy let zombies accumulate unseen, and a
dead proxy could not restart itself. The external daemon was the answer. It
retired at `3a0c58e` with the proxy it supervised — Ollama's single tier has
its own residency management — but the supervisory principle (an external
monitor for a self-supervising service) is the durable knowledge the archive
preserves.

## Interfaces

The watchdog monitored the proxy, killed zombies, and restarted the proxy as
needed. No live callers remain.

## Gotchas

The two-failure-mode distinction it drew — proxy-crash versus
proxy-stuck-with-zombies — is the design insight worth keeping even though
the supervised service is gone.
