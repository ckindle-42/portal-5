---
id: unit-lab-setup-verification
kind: what
title: "LAB_SETUP \u2014 Verification"
sources:
- type: code
  path: scripts/lab_ready.py
- type: code
  path: scripts/lab_discover.py
- type: code
  path: scripts/verify_attack_image.py
- type: code
  path: scripts/lab_host.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.521833
updated_at: 1784946220.521833
---

Verification uses the scripts themselves, not the doc. `python3 scripts/lab_ready.py`
runs the full readiness gate and exits zero only when every required check is
GREEN. `python3 scripts/lab_discover.py` probes the live LXC 112 state read-only
through `scripts/lab_host.py` and writes the report to lab_discovery.json in the
repo root. `python3 scripts/verify_attack_image.py config/attack_image_contract.json`
checks every required tool, file, and runtime probe against the contract and
exits zero when the attack image satisfies it, failing the build otherwise.

## Why

These three commands cover the three distinct readiness questions: whether the
host-side gate passes, what the live lab actually reports from a probe that
writes nothing, and whether the attack image's manifest matches the contract
exactly. Using them together catches a stale image or a drifted host before any
benchwork starts.
