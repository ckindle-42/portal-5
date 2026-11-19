---
id: unit-SECURITY_BENCH_EXEC-quick-reachability-test-from-within-dind
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Quick reachability test from within DinD"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Quick reachability test from within DinD
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

docker exec portal5-dind docker run --rm --net bridge portal5-attack:latest \
  sh -c 'nxc smb 10.10.11.21 2>&1 | tail -2 && redis-cli -h 10.10.11.50 ping && \
         nxc smb 10.10.11.10 -u "" -p "" 2>&1 | head -3 && \
         curl -s -o /dev/null -w "%{http_code}" http://10.10.11.50:80/'
