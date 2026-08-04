---
id: unit-security-tests-test-objective-executor
kind: what
title: SecurityExecutor ground-truth boundary tests
sources:
- type: code
  path: portal/modules/security/tests/test_objective_executor.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_objective_executor.py` pins `SecurityExecutor` as the ground-truth boundary between a model's decision and the lab. A monkeypatched `lab_dispatch` records every call, proving the executor invokes the real tool path with the declared arguments and returns the raw output untouched. The scope guard fires before any action leaves the box, raising `OutOfScopeError` for an out-of-bounds target, and the observation delta never carries the model's predicted `expected_observation_delta` narration. Read-only binaries on the allowlist dispatch under their own name while non-allowlisted tools retain the capability fallback so dispatch stays bounded. When a `LabPerception` is bound, live perception is folded into the delta as ground truth, and oracle results come from `verify_finding` rather than the model's prediction.

## Why

The executor is where a model's confidence and narration must stop being trusted and real lab output must start. If the predicted delta leaked into observations, the whole scoring loop would be confirming the model's story instead of the actual state, so the suite forbids that leak explicitly and proves the scope guard and perception merge run before any action reaches the sandbox.
