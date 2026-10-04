---
id: unit-compliance-served-window
kind: mixed
title: "Compliance served-window resolver — what a seat actually serves"
sources:
- type: code
  path: portal/modules/compliance/core/served_window.py
- type: code
  path: scripts/compliance/truth/data_integrity.py
- type: code
  path: tests/unit/test_compliance_data_truth_instruments.py
claims:
- probe: compliance.served_window.tag_window
  equals: 32768
confidence: high
tags:
- compliance
- retrieval
- windows
---

`portal.modules.compliance.core.served_window` resolves one workspace
`model_hint` to the window the engine actually serves, from `config/backends.yaml`
data plus a short engine probe.

## Why

It exists because of TASK_COMPLIANCE_DATA_TRUTH_V1 (F8): `compliance-reading`
declared `context_limit: 32768` while the `ctx32k` alias served the 262,144-token
MLX conversion on oMLX, so `compliance_context` refused whole material that fit
and nothing could see the fiction. The drift was invisible because no code
compared the two numbers.

A hint can be servable by more than one backend — listed natively on the Ollama
backend and aliased to an MLX conversion on oMLX — and the routes need not agree
on a window, so the resolver probes every in-group route (`workspace_routing`
groups, the router's tier 1) and reports each answer plus the disagreement;
out-of-group routes are recorded as notes. Probes never raise: an unreachable
engine is an unknown window with the reason attached, never a zero. The tag's
`-ctxNk` suffix is a record, not a gate — tag names round colloquially
(`ctx98k` bakes 98304) and a workspace may legitimately declare less than its
seat bakes. `scripts/compliance/truth/data_integrity.py` consumes the resolver
for the declared=served integrity check, and the window guard prices through it
after DATA_TRUTH D7.
