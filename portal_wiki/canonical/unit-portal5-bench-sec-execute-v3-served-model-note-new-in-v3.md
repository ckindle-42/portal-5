---
id: unit-portal5-bench-sec-execute-v3-served-model-note-new-in-v3
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Served-model note (new in V3)"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: Served-model note (new in V3)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.7091782
updated_at: 1784946220.7091782
---

Two security-adjacent personas were served-model-corrected recently
(`model_pin`). If the bench qualifies a *persona* (not a bare workspace),
confirm it's served its pinned model — a security persona benched on the wrong
model produces a meaningless capability score. The preflight lists all
`model_pin` personas; cross-check any that appear in your run.

---
