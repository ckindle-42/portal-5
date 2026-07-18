---
id: unit-blue-orchestration-v2-capture-gap
kind: why
title: 'Blue Orchestration V2: capture-pipeline gap FIXED+live-verified; needs fresh
  recapture before Slice 8'
sources:
- type: design
  path: coding_task/BUILD PROGRAM SEC BLUE ORCHESTRATION V2.md
  section: Slice 8
- type: code
  path: portal/modules/security/core/siem/collect.py
  commit: 394fb78e
- type: code
  path: portal/modules/security/core/exec_chain.py
  commit: 394fb78e
- type: scenario
  path: portal/modules/security/core/results/captures/
  section: asrep_to_lateral, kerberoast_to_da, meta3_tomcat_manager
last_generated_commit: ''
confidence: high
tags:
- security
- blue-team
- open-item
- known-limitation
- blue-orchestration-v2
- telemetry-capture
created_at: 1784337080.223121
updated_at: 1784337080.223121
---


