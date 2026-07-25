---
id: unit-portal5-bench-sec-execute-v3-autonomous-monitoring-loop-required-default
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Autonomous Monitoring Loop \u2014 required\
  \ default"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: "Autonomous Monitoring Loop \u2014 required default"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.706641
updated_at: 1784946220.706641
---

Security chains are slow (thinking models + tool round-trips; per-workspace
timeouts up to 1500s). Establish a `ScheduleWakeup` loop immediately after
launch, same pattern as the TPS bench: check liveness + progress every 20–30
min, skip-and-note a hung workspace, halt with evidence if stalled.

---
