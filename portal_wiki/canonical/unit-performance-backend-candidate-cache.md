---
id: unit-PERFORMANCE-backend-candidate-cache
kind: why
title: "PERFORMANCE \u2014 Backend Candidate Cache"
sources:
- type: design
  path: docs/PERFORMANCE.md
  section: Backend Candidate Cache
last_generated_commit: ''
confidence: high
tags:
- docs
- PERFORMANCE
created_at: 1783195000.8808389
updated_at: 1783195000.8808389
---

`get_backend_candidates()` results are cached with a 5-second TTL. Cache is invalidated after health checks. Avoids list comprehension and `random.shuffle()` on every request.
