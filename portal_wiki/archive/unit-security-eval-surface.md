---
id: unit-security-eval-surface
kind: mixed
title: "Security eval surface \u2014 re-export boundary for bench harnesses"
sources:
- type: code
  path: portal/modules/security/eval/__init__.py
  commit: 1d62c01d
last_generated_commit: 1d62c01d
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- eval
created_at: 1785795976.101092
updated_at: 1785795976.101092
---

The eval subpackage is the public re-export boundary for the security
module's eval, bench, and drift harnesses. The RBP engine's eval code stays in
`core/`; this surface exposes the stable entry points other code should call
rather than importing `core.agentic_blue_eval`, `core.candidate_eval`, or
`core.rescore_run` internals directly.

## Why

The same facade discipline as the knowledge surface: core internals may be
reorganised freely as long as this stable boundary keeps serving the same
entry points. Code that drives a bench — a campaign supervisor, a UAT driver,
an operator script — should import from here so it does not reach into the
moving internals of the RBP engine. This is what keeps the eval harnesses
consumable without importing the whole security core.

## Interfaces

`run_eval` (agentic blue eval), `candidate_eval_main` (candidate evaluation),
`rescore` (result re-scoring), and the two blue-detection scoring functions
(`score_blue_detections`, `score_blue_detections_diagnostic`) are re-exported
through `__all__`.
