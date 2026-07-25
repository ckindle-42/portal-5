---
id: unit-lab-setup-lane-targets
kind: what
title: "LAB_SETUP \u2014 Lane Targets"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: Lane Targets
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.520834
updated_at: 1784946220.520834
---

```bash
./launch.sh lab-web-up   / lab-web-down      # SPA target (browser/OAST)
./launch.sh lab-cloud-up / lab-cloud-down    # LocalStack+kind (cloud)
./launch.sh oast-up      / oast-down         # OAST collaborator
```
