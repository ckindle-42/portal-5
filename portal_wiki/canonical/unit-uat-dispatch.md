---
id: unit-uat-dispatch
kind: mixed
title: "UAT dispatch \u2014 preset/tool dispatch"
sources:
- type: code
  path: tests/uat/dispatch.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799302.2489102
updated_at: 1785799302.2489102
---

The dispatch logic that routes a UAT request to the right preset or tool, including the `_PresetUnreachableError` handling split from the monolith.

## Why

Dispatch is where a UAT request becomes a concrete call, and the module owns the preset resolution and the unreachable-preset failure mode. Keeping the dispatch separate from the runner is what lets the unreachable case be tested as its own error path rather than tangled in the run flow.

## Interfaces

The dispatch functions and `_PresetUnreachableError`.

## Gotchas

The unreachable-preset error must be raised distinctly — a caller that swallows it would report a silent no-op as a pass.
