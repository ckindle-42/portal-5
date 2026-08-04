---
id: unit-tests-unit-test-lab-setup
kind: what
title: Lab setup, readiness, and targets unit tests
sources:
- type: code
  path: tests/unit/test_lab_setup.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_lab_setup.py` covers the lab lifecycle scripts in dry-run or synthetic mode, so nothing needs Docker or a network. The setup path runs idempotently and respects the heavy-skip flag, readiness returns a boolean alongside a result list that includes required checks, and the port probe is pinned to a pid-1-safe netcat invocation. The targets layer lists the catalog and honours dry-run for both the friendly name and the raw path forms of a target. The attack-manifest tests verify the readiness gate turns GREEN only for a complete, current manifest and RED for a stale or incomplete one, and that `verify` from `verify_attack_image` correctly reports missing tools, missing or empty required files, and failing runtime smoke checks.

## Why

These scripts run against a live lab that is expensive to bring up and easy to disrupt, so their behaviour must be provable without ever starting containers. Dry-run and manifest verification exercise the same decision logic the real commands use, which catches wiring mistakes — like the netcat flags or the manifest hash check — before an operator wastes time standing up the environment.
