---
id: unit-portal5-acceptance-execute-v9-non-negotiables
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Non-negotiables"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: portal/platform/inference/config.py
- type: code
  path: tests/acceptance/runner.py
- type: code
  path: scripts/routing_regression.py
- type: code
  path: tests/acceptance/s10_personas_ollama.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.697818
updated_at: 1784946220.697818
---

Run the preflight first: `scripts/execute_preflight.py` prints the live
production workspace count from `config/portal.yaml` and the persona catalog
size, so acceptance targets the current surface rather than a baked number.
`PORTAL_ENABLE_EVAL` must be unset for acceptance runs: when it is unset, the
eval module's workspaces are excluded by `get_workspace_dict` via
`_eval_enabled` in `portal/platform/inference/config.py`, and the runner's
`ALL_SECTIONS` registers no bench sections, keeping the suite on production
workspaces.

Product code under `portal/` is read-only during acceptance: a regression is
reported with evidence, never hidden by loosening acceptance expectations. The
routing-baseline check and the served-model checks are pass/fail signal, not
advisory — a baseline drift in `scripts/routing_regression.py` or a served-model
mismatch in S10 is a failure to act on, per the mismatch-to-WARN handling in
`s10_personas_ollama.py`.

## Why

These rules keep the acceptance suite measuring the product instead of
defending it. A config-driven preflight prevents tests from targeting a stale
catalog after a collapse or expansion; keeping eval workspaces and bench
sections out bounds the run to what production actually serves; and refusing to
loosen expectations means a routing regression surfaces immediately rather than
as silent drift behind green results.
