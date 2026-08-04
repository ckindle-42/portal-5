---
id: unit-SECURITY_BENCH_EXEC-clock-skew-krb-ap-err-skew
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Clock skew (KRB_AP_ERR_SKEW)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Clock skew (KRB_AP_ERR_SKEW)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.911745
updated_at: 1783195000.911745
---

`_ensure_lab_time_sync()` auto-syncs via `ntpdate` or `rdate` before first dispatch.
