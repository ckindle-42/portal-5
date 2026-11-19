---
id: unit-LAB_SETUP-lane-targets
historical: true
kind: why
title: "LAB_SETUP \u2014 Lane Targets"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: Lane Targets
confidence: high
tags:
- docs
- LAB_SETUP

---


```bash
./launch.sh lab-web-up   / lab-web-down      # SPA target (browser/OAST)
./launch.sh lab-cloud-up / lab-cloud-down    # LocalStack+kind (cloud)
./launch.sh oast-up      / oast-down         # OAST collaborator
```
