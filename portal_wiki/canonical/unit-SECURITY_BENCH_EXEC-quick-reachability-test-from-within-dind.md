---
id: unit-SECURITY_BENCH_EXEC-quick-reachability-test-from-within-dind
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Quick reachability test from within DinD"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Quick reachability test from within DinD
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.8974552
updated_at: 1783195000.8974552
---

docker exec portal5-dind docker run --rm --net bridge portal5-attack:latest \
  sh -c 'nxc smb 10.10.11.21 2>&1 | tail -2 && redis-cli -h 10.10.11.50 ping && \
         nxc smb 10.10.11.10 -u "" -p "" 2>&1 | head -3 && \
         curl -s -o /dev/null -w "%{http_code}" http://10.10.11.50:80/'
