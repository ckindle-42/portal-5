---
id: unit-archive-mlx-readiness
kind: mixed
title: "MLX readiness watcher \u2014 archived health-to-file poller"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-readiness.py
  commit: 2d2e9c0f
last_generated_commit: 2d2e9c0f
claims: []
confidence: high
tags:
- authored-v1
- archive
- mlx
created_at: 1785797141.7325509
updated_at: 1785797141.7325509
---

This is the MLX proxy readiness watcher, archived with the retired MLX
stack: it polled the proxy's health endpoint and wrote a readiness state file
so the UAT driver and other tools could read a stable file instead of
implementing their own wait-and-see timer loops.

## Why

The watcher encoded a real testing lesson: timing-based readiness checks in
each test are fragile and duplicated, so decoupling readiness into a
background poller that writes one state file let every consumer read the same
truth. It was retired with the proxy at `3a0c58e` because the thing it
polled no longer exists — the archive records that the pattern itself (a
shared readiness state file decoupling polling from consumers) was sound and
could be reused if a future subsystem needs the same decoupling.

## Interfaces

The watcher polled `/health` and wrote `/tmp/portal5-mlx-readiness.json`. No
live callers remain.

## Gotchas

The state file path was `/tmp` — deliberately ephemeral, matching the
short-lived nature of the readiness signal it carried.
