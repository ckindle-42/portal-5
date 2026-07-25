---
id: unit-portal5-acceptance-execute-v9-autonomous-monitoring-loop-required-default
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Autonomous Monitoring Loop \u2014 required\
  \ default"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: "Autonomous Monitoring Loop \u2014 required default"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.694719
updated_at: 1784946220.694719
---

Full suite is ~82 min (S10c compliance personas ~50 min alone). Establish a
`ScheduleWakeup` loop immediately after launching; check liveness + section
progress every ~15 min; diagnose stalls; halt with evidence if hung.

---
