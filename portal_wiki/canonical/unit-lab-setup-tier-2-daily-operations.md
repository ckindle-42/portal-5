---
id: unit-lab-setup-tier-2-daily-operations
kind: what
title: "LAB_SETUP \u2014 Tier 2 \u2014 Daily Operations"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: "Tier 2 \u2014 Daily Operations"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.51969
updated_at: 1784946220.51969
---

```bash
./launch.sh lab-up               # start the core lab stack
./launch.sh lab-up-wazuh         # start telemetry (Wazuh/WinEvent)
./launch.sh lab-ready            # readiness gate — GREEN = ready to bench
```
