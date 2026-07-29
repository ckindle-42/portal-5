---
id: unit-blue-orchestration-v2-capture-gap
kind: why
title: 'Blue Orchestration V2: capture pipeline fixed, full 89-scenario corpus recaptured'
sources:
- type: code
  path: portal/modules/security/core/siem/collect.py
  commit: 8acfdca5
- type: code
  path: scripts/lab_targets.py
  commit: c084cea4
- type: code
  path: portal/modules/security/core/exec_chain.py
  commit: 394fb78e
- type: scenario
  path: bench-run:sec-bench-red-recapture:2026-07-18
  section: full 89-scenario recapture sweep
last_generated_commit: ''
confidence: high
tags:
- security
- blue-team
- open-item
- known-limitation
- blue-orchestration-v2
- telemetry-capture
created_at: 1784366416.7372081
updated_at: 1784366416.7372081
---

