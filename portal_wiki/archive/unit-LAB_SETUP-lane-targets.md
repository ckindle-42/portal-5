---
id: unit-LAB_SETUP-lane-targets
kind: why
title: "LAB_SETUP \u2014 Lane Targets"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: Lane Targets
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_SETUP
created_at: 1783195000.868927
updated_at: 1783195000.868927
---


```bash
./launch.sh lab-web-up   / lab-web-down      # SPA target (browser/OAST)
./launch.sh lab-cloud-up / lab-cloud-down    # LocalStack+kind (cloud)
./launch.sh oast-up      / oast-down         # OAST collaborator
```
