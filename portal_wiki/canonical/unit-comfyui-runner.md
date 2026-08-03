---
id: unit-comfyui-runner
kind: mixed
title: "ComfyUI acceptance runner \u2014 section sequencing"
sources:
- type: code
  path: tests/comfyui/runner.py
  commit: 441fd2a1
last_generated_commit: 441fd2a1
claims: []
confidence: high
tags:
- authored-v1
- tests
- comfyui
created_at: 1785798957.316152
updated_at: 1785798957.316152
---

`runner.py` orchestrates the ComfyUI acceptance sections: it defines the
C0-C11 section functions, parses the section selection spec, and runs the
chosen sections in order, collecting the results.

## Why

The runner is the sequencing layer: ComfyUI sections have dependencies (C0
prereqs before C1 direct API, C3 discovery before C4 generation) and the
runner is what enforces the order and the section-selection semantics. The
section functions themselves delegate to the C-modules so the runner stays
a thin coordinator rather than growing the acceptance logic into itself.

## Interfaces

`C0`-`C11` are the section function stubs that delegate to the C-modules;
`_parse_sections` and `run_sections` handle selection and orchestration.

## Gotchas

Order matters — running C4 without C0 having confirmed prereqs produces a
misleading failure, which is why the runner enforces the canonical order
rather than letting arbitrary selection reorder the stack.
