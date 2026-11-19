---
id: unit-LAB_SETUP-tier-2-daily-operations
historical: true
kind: why
title: "LAB_SETUP \u2014 Tier 2 \u2014 Daily Operations"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: "Tier 2 \u2014 Daily Operations"
confidence: high
tags:
- docs
- LAB_SETUP

---


```bash
./launch.sh lab-up               # start the core lab stack
./launch.sh lab-up-wazuh         # start telemetry (Wazuh/WinEvent)
./launch.sh lab-ready            # readiness gate — GREEN = ready to bench
```
