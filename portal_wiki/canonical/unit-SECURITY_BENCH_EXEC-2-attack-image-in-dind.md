---
id: unit-SECURITY_BENCH_EXEC-2-attack-image-in-dind
kind: why
title: "SECURITY_BENCH_EXEC \u2014 2. attack image in DinD"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 2. attack image in DinD
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.897689
updated_at: 1783195000.897689
---


```bash
docker exec portal5-dind docker images portal5-attack 2>/dev/null | grep latest
