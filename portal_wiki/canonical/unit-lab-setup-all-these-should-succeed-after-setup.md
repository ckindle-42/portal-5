---
id: unit-lab-setup-all-these-should-succeed-after-setup
kind: what
title: "LAB_SETUP \u2014 All these should succeed after setup:"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: 'All these should succeed after setup:'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.522325
updated_at: 1784946220.522325
---

./launch.sh setup --skip-heavy --dry-run
./launch.sh lab-ready
python3 scripts/lab_targets.py up struts2/s2-045 --dry-run
python3 scripts/lab_targets.py list | wc -l   # ≥ 7 targets
```
