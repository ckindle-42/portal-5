---
id: unit-wiki-adapter-writeback-module
kind: mixed
title: "Wiki module write-back \u2014 unit-as-state toggle"
sources:
- type: code
  path: portal/platform/wiki/adapters/writeback_module.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797615.073633
updated_at: 1785797615.073633
---

The module write-back adapter flips a `unit-module-<name>` unit's fenced
yaml `enabled:` field when a module is toggled — the wiki unit *is* the
state, not a separate event log, so `enabled_modules()` always reads current
truth with no replay step.

## Why

Using the unit as the state, rather than a log of state changes, is the
design that makes the toggle read-back trivial: no event replay, no eventual
consistency — the resolver reads the unit and gets the truth. The confirm
gate on the flip keeps a module enable/disable from being a silent one-line
write; an operator or a trusted CLI confirms it.

## Interfaces

`module_state_change(name, from_state, to_state, actor, auto_confirm)` props
the flip through the propose path.

## Gotchas

Because the unit is the state, the from/to states matter for the proposal —
the adapter records the transition, and the resolver trusts the resulting
unit body, so the write must be complete, not partial.
