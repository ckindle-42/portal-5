---
id: unit-inference-config-validate
kind: mixed
title: "Inference config validate \u2014 fast sync-config pre-gate"
sources:
- type: code
  path: portal/platform/inference/config_validate.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785797754.624181
updated_at: 1785797754.624181
---

`config_validate.py` is a fast, self-contained validator for
`config/portal.yaml` used as a pre-regeneration gate: it runs on the
`sync-config` hot path and checks the invariants whose violation would
corrupt the derived artifacts. It returns a list of error strings and never
raises on malformed input.

## Why

`sync-config` regenerates the derived files from the portal config, so a
malformed config would silently corrupt every downstream artifact. The
validator catches that *before* regeneration, cheaply and independently of
the heavyweight validate harness — it is a focused gate for the invariants
that matter to the generators (boolean keys in the right place, structural
requirements), not a full system validation. Never raising is part of the
contract: on malformed input it reports the errors rather than crashing the
sync path.

## Interfaces

The module exports the validation entry point returning the error list, and
the `_BOOL_KEYS` tuple of keys that must be boolean.

## Gotchas

It is deliberately *not* `scripts/validate_system.py` — that harness is for
the full 74-check run; this is the fast dependency-light gate on the sync hot
path.
