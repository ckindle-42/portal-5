---
id: unit-LAB_SETUP-tier-2-daily-operations
kind: why
title: "LAB_SETUP \u2014 Tier 2 \u2014 Daily Operations"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: "Tier 2 \u2014 Daily Operations"
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_SETUP
created_at: 1783195000.868466
updated_at: 1783195000.868466
---


```bash
./launch.sh lab-up               # start the core lab stack
./launch.sh lab-up-wazuh         # start telemetry (Wazuh/WinEvent)
./launch.sh lab-ready            # readiness gate — GREEN = ready to bench
```
