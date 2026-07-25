---
id: unit-performance-backend-candidate-cache
kind: what
title: "PERFORMANCE \u2014 Backend Candidate Cache"
sources:
- type: doc
  path: docs/PERFORMANCE.md
  commit: 05e42ec2
  section: Backend Candidate Cache
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.510197
updated_at: 1784946220.510197
---

`get_backend_candidates()` results are cached with a 5-second TTL. Cache is invalidated after health checks. Avoids list comprehension and `random.shuffle()` on every request.
