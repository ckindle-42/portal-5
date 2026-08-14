---
id: unit-performance-backend-candidate-cache
kind: what
title: "PERFORMANCE \u2014 Backend Candidate Cache"
sources:
- type: code
  path: portal/platform/inference/cluster_backends.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.510197
updated_at: 1784946220.510197
---

`BackendRegistry.get_backend_candidates()` caches its per-workspace result in `_candidate_cache` with a 5-second TTL (`_candidate_cache_ttl = 5.0`). A cache hit returns a fresh list copy without re-scanning the healthy backend list, re-running the group-priority sort, or calling `random.shuffle()` on the fallback tiers.

The cache is invalidated eagerly, not just TTL-expired: `_refresh_healthy_cache()` calls `_invalidate_candidate_cache()` after every `health_check_all()` cycle, so a backend that just went unhealthy drops out of routing within one health cycle (30s default) instead of lingering until its TTL entry ages out. Unknown workspace ids are clamped to `_unknown` so the cache dict cannot grow unbounded.

## Why

The candidate-selection cost matters because it runs on the hot path of every request that names a workspace, while backend health only changes on the 30-second health cycle. Without the cache each request would rebuild the ordered candidate list from the full backend table, paying a list comprehension plus a shuffle per group even though nothing changed. The cache converts that steady-state cost into one dict get and a list copy, and the health-cycle invalidation guarantees freshness on the timescale that actually matters: the moment a backend becomes unhealthy.
