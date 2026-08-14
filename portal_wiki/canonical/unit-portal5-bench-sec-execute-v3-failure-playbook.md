---
id: unit-portal5-bench-sec-execute-v3-failure-playbook
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Failure playbook"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/_data.py
- type: code
  path: portal/platform/inference/router/preinject.py
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.710026
updated_at: 1784946220.710026
---

- `--workspaces auto-pentest` errors — `auto-pentest` is a retired alias (it is
  in `RETIRED_ALIASES` in `scripts/execute_preflight.py`) and is not registered
  in `config/portal.yaml`, so `call_pipeline` forwards it as the pipeline
  `model` and the request fails. Switch to `auto-security::pentest`.
- Variant resolves to base with no variant behavior — the `::` key must name a
  real `variants:` sub-block on `auto-security` in `config/portal.yaml`;
  `_resolve_workspace_variant` in the router only fabricates a synthetic
  workspace when the named variant is defined.
- Lab RED — resolve per `docs/LAB_SETUP.md` and re-run `scripts/lab_ready.py`;
  do not bench a cold lab.
- Chain times out — confirm `_data.py`'s `PER_WORKSPACE_TIMEOUT` has a literal
  `::`-keyed entry for the workspace (for example `auto-security::redteam`); a
  folded variant that lost its cap falls back to `REQUEST_TIMEOUT` and may be
  killed mid-chain. The edcaa8b fix keyed that dict on the literal `::` string
  precisely to stop this, so verify the key survived any later fold.

## Why

Each entry is a previously-hit failure with a specific mechanical cause. The
retired-alias and timeout entries both trace to one design decision: the
harness addresses variants by their literal `::` string, so aliases and
uncapped folds fail in ways that look like model faults but are vocabulary
faults. The playbook names the code that decides each outcome.
