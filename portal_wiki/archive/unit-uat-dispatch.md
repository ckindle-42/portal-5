---
id: unit-uat-dispatch
historical: true
kind: mixed
title: "UAT dispatch \u2014 preset/tool dispatch"
sources:
- type: code
  path: tests/uat/dispatch.py
  commit: d7dcc96a
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat

---

The dispatch logic that routes a UAT request to the right preset or tool, including the `_PresetUnreachableError` handling split from the monolith.

## Why

Dispatch is where a UAT request becomes a concrete call, and the module owns the preset resolution and the unreachable-preset failure mode. Keeping the dispatch separate from the runner is what lets the unreachable case be tested as its own error path rather than tangled in the run flow.

## Interfaces

The dispatch functions and `_PresetUnreachableError`.

## Gotchas

The unreachable-preset error must be raised distinctly — a caller that swallows it would report a silent no-op as a pass.
