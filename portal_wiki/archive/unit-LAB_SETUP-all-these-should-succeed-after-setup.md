---
id: unit-LAB_SETUP-all-these-should-succeed-after-setup
kind: why
title: "LAB_SETUP \u2014 All these should succeed after setup:"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: 'All these should succeed after setup:'
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_SETUP
created_at: 1783195000.869597
updated_at: 1783195000.869597
---

./launch.sh setup --skip-heavy --dry-run
./launch.sh lab-ready
python3 scripts/lab_targets.py up struts2/s2-045 --dry-run
python3 scripts/lab_targets.py list | wc -l   # ≥ 7 targets
```
