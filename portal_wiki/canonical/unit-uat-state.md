---
id: unit-uat-state
kind: mixed
title: "UAT state \u2014 per-run mutable state"
sources:
- type: code
  path: tests/uat/state.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799264.505173
updated_at: 1785799264.505173
---

The mutable per-run state: the routing log, chat ids, and archival state that a UAT run accumulates.

## Why

The state must be visible to every module in the driver, and the attribute-form access rule (`state._ROUTING_LOG`, never a value import) is what makes rebinding visible everywhere. This is the difference between a run whose modules agree on the current state and one where each module holds a stale copy.

## Interfaces

`_ROUTING_LOG`, `_run_folder_id`, and the other state attributes, accessed attribute-form.

## Gotchas

A value-copied import (`from state import _ROUTING_LOG`) would freeze the state at import time — the attribute-form rule exists specifically to prevent that.
