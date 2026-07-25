---
id: unit-portal5-bench-sec-execute-v3-candidate-qualification-report
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Candidate qualification report"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_SEC_EXECUTE_V3.md
  commit: 05e42ec2
  section: Candidate qualification report
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.709623
updated_at: 1784946220.709623
---

1. Per variant: engagement rate, structured-output adherence, tool-call
   ordering correctness, chain completion.
2. For execution workspaces: did the live-lab steps actually execute and get
   detected (if Wazuh up)?
3. Promotion recommendation per DESIGN's PROMOTE_POLICY — **zero auto-
   promotions**; a passing candidate is a recommendation for operator action +
   a bench-gate clearance record, never an automatic primary swap.
4. Commit the results JSON + any dashboard update.

---
