---
id: unit-portal5-bench-execute-v4-on-each-wakeup
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 On each wakeup"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: On each wakeup
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.702064
updated_at: 1784946220.702064
---

1. Is the process alive? (`ps`), how far along? (tail the log, count completed
   tests vs planned).
2. If progressing: reschedule ~20–30 min out.
3. If stalled (no new completed test in ~2 cooldown intervals): diagnose — a
   model that won't load, an OOM, a hung backend. Note it, and either skip the
   offending model (`--skip-model <id>`) and continue, or halt with evidence.
4. If finished: proceed to results + dashboard.

---
