---
id: unit-SECURITY_BENCH_EXEC-clock-skew-krb-ap-err-skew
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Clock skew (KRB_AP_ERR_SKEW)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Clock skew (KRB_AP_ERR_SKEW)
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

`_ensure_lab_time_sync()` auto-syncs via `ntpdate` or `rdate` before first dispatch.
