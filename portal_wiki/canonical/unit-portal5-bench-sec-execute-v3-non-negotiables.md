---
id: unit-portal5-bench-sec-execute-v3-non-negotiables
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Non-negotiables"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/candidate_eval.py
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.7105012
updated_at: 1784946220.7105012
---

- Run `scripts/execute_preflight.py` first and use its live `security_variants`
  list, never a baked table — the variant set is config-driven in
  `config/portal.yaml`.
- Address workspaces canonically as `auto-security::<variant>`; the
  pre-collapse aliases (`auto-redteam`, `auto-blueteam`, `auto-pentest`,
  `auto-purpleteam*`) are retired and the alias shim is gone, enforced by the
  `RETIRED_ALIASES` gate in the preflight.
- Confirm green `python3 scripts/lab_ready.py` before any `--lab-exec` run; the
  bench's own `verify_lab_targets_reachable` gate also aborts live chain runs on
  unreachable DC/SRV targets unless `--force-unreachable-lab` is passed.
- Product code under `portal/` is read-only for the execute agent, and promotion
  policy is `PROMOTE_POLICY=confirm` — zero auto-promotions; a passing candidate
  is a recommendation for operator action, never an automatic primary swap.

## Why

These four are the load-bearing rules the execution model rests on. Preflight
is the only current source of variant names, the canonical key is the only
vocabulary both harness and router accept, the lab gates exist because a cold
lab yields hours of meaningless zeros, and confirm-only promotion keeps a
benchmark artifact from ever editing fleet config on its own.
