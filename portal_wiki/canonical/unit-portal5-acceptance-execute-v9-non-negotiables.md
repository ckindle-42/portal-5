---
id: unit-portal5-acceptance-execute-v9-non-negotiables
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Non-negotiables"
sources:
- type: doc
  path: tests/PORTAL5_ACCEPTANCE_EXECUTE_V9.md
  commit: 05e42ec2
  section: Non-negotiables
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.697818
updated_at: 1784946220.697818
---

- Preflight first; 21 production workspaces is the current truth, printed live.
- `PORTAL_ENABLE_EVAL` unset for acceptance.
- Product code read-only; regressions get reported, never masked by loosening
  acceptance expectations.
- Routing baseline + served-model checks are pass/fail signal, not advisory.
