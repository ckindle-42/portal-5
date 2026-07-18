---
id: unit-blue-orchestration-v2-capture-gap
kind: why
title: 'Blue Orchestration V2: capture pipeline fixed, full 89-scenario corpus recaptured'
sources:
- type: design
  path: coding_task/BUILD PROGRAM SEC BLUE ORCHESTRATION V2.md
  section: Slice 8
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
  path: portal/modules/security/core/results/sec_bench_red_recapture_20260718.json
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


