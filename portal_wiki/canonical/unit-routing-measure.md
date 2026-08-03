---
id: unit-routing-measure
kind: mixed
title: "Routing integrity measurement \u2014 keyword router before/after diff"
sources:
- type: code
  path: tests/routing/measure.py
  commit: dfa74e2e
last_generated_commit: dfa74e2e
claims: []
confidence: high
tags:
- authored-v1
- tests
- routing
created_at: 1785795508.2065651
updated_at: 1785795508.2065651
---

`measure.py` runs the keyword-layer (deterministic) router against the
routing-integrity corpus and writes a JSON result file. It is run once against
a pre-collapse checkout and once against the current tree so the two outputs
can be diffed for routing regressions introduced by the workspace collapse.

## Why

The measurement must be comparable across two different code states, which is
why the corpus is always read from the *current* tree's versioned copy even
when the script executes from a pre-collapse worktree — and why alias
resolution falls back gracefully. A pre-collapse tree has no
`_unpack_synthetic_workspace` to import, so `_resolve_alias` returns the id
unchanged as a bare base when the import fails, letting the same script run in
both worlds. The `served_model` field resolves the workspace's current
`model_hint` (plus variant) so the output shows not just which workspace won
but which model would actually serve it.

## Interfaces

`main()` reads the corpus (explicit `--corpus` or the default path), calls
`_detect_workspace` on each message, resolves alias and served model, and
writes the sorted-by-id result dict to `--out`. `_resolve_alias` handles the
canonical `base::variant` form and the legacy synthetic workspace form;
`_resolve_model` reads `model_hint` from `config/portal.yaml`.

## Gotchas

The import of `_detect_workspace` happens inside `main`, not at module top, so
a pre-collapse tree that lacks that exact symbol still loads the script far
enough to produce a structured error rather than a crash at import time.
