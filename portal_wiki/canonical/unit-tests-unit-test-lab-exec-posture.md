---
id: unit-tests-unit-test-lab-exec-posture
kind: what
title: Lab-exec posture selection unit tests
sources:
- type: code
  path: tests/unit/test_lab_exec_posture.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_lab_exec_posture.py` verifies that the code sandbox MCP selects its execution posture from environment flags alone, with no Docker daemon or network involved. Each test reimports the module fresh via a helper that clears the relevant variables and then sets the ones under test, so the module-level posture constants re-resolve on every case. The default posture is locked down: `SANDBOX_LAB_EXEC` and `SANDBOX_ALLOW_NETWORK` are both false and `_resolve_image` returns the stock image unchanged. Enabling lab exec swaps in the attack image when `SANDBOX_LAB_IMAGE` is supplied, falls back to the default image when it is absent, injects the lab target and meta3 credential values into the resolved module state, and relies on the documented vagrant defaults when nothing is set.

## Why

The sandbox is shared infrastructure used by both benign coding workspaces and the security lab, so its posture must be decided by configuration rather than by which container happens to be running. Reimporting the module per test keeps the assertions honest about pure logic, and the locked-down default guarantees that a misconfigured host degrades to the safe posture instead of silently enabling the attack envelope.
