---
id: unit-portal-conftest
kind: mixed
title: "Portal test-tree conftest \u2014 module-test CI posture"
sources:
- type: code
  path: portal/conftest.py
  commit: 1a0e2df4
claims: []
confidence: high
tags:
- authored-v1
- tests
- conftest
created_at: 1785794846.829962
updated_at: 1785794846.829962
---

The portal test-tree conftest gives module tests under `portal/` the same
deterministic CI posture that `tests/conftest.py` already gives the top-level
suite. pytest's conftest discovery is hierarchy-scoped, so a conftest under
`tests/` never applies to sibling trees like `portal/modules/security/tests/`;
this file mirrors the environment defaults there so every module test tree
behaves identically without copying the logic per module.

## Why

Router-pipe module-level imports call `sys.exit(1)` when `PIPELINE_API_KEY` is
unset, so any test that imports the pipeline without a key dies at collection
time with a confusing failure. Setting the key via `setdefault` before any
`portal.platform.inference` import makes the failure mode impossible. The same
`setdefault` discipline applies to the `LAB_*` variables: CI's clean shell has
no lab targets, and a missing `LAB_TARGET_DC` used to mean "works locally,
fails CI" — defaulting them empty gives dry-run behaviour deterministically
while a populated local `.env` still overrides.

## Interfaces

The file has no functions; its entire surface is side effects at import time.
`PIPELINE_API_KEY` is defaulted for the inference import guard, the seven
`LAB_*` and `SANDBOX_LAB_EXEC` variables are defaulted for the lab posture,
and a bare interpreter (no active venv) gets the repo `.venv` site-packages
inserted into `sys.path` so a fresh Python can find the editable install.

## Gotchas

The venv path probe only fires when `sys.prefix == sys.base_prefix` — inside an
active venv the editable install is already importable and inserting a second
site-packages would risk version skew.
