---
id: unit-SECURITY_BENCH_EXEC-2-models-are-hitting-real-ips
kind: why
title: "SECURITY_BENCH_EXEC \u2014 2. Models are hitting real IPs"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 2. Models are hitting real IPs
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.910135
updated_at: 1783195000.910135
---


```bash
grep "10\.10\.11\.21\|10\.10\.11\.10\|portal\.lab\|LabAdmin1" /tmp/secbench_kerberoast.log
```

If you see `10.10.10.100` or `10.10.10.161` (HTB training IPs), the `_sub_hint()` substitution isn't working.
