---
id: unit-lab-setup-all-these-should-succeed-after-setup
kind: what
title: "LAB_SETUP \u2014 All these should succeed after setup:"
sources:
- type: code
  path: scripts/lab_setup.py
- type: code
  path: scripts/lab_ready.py
- type: code
  path: scripts/lab_targets.py
- type: code
  path: config/lab_targets.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.522325
updated_at: 1784946220.522325
---

After a successful lab setup these commands must all exit cleanly; they are the
first checks an operator runs to confirm the provisioned environment is usable
without re-downloading anything.

python3 scripts/lab_setup.py --skip-heavy --dry-run
python3 scripts/lab_ready.py
python3 scripts/lab_targets.py up struts2/s2-045 --dry-run
python3 scripts/lab_targets.py list

## Why

The dry-run flags make the first three checks safe on a machine that has no
attack image yet: `setup` prints its plan, the target `up` path resolves the
vulhub compose path without starting it, and `lab_ready` reports which required
components are missing. The `list` command simply prints the catalog from
`config/lab_targets.yaml`, so it is the cheapest sanity check of the group.
