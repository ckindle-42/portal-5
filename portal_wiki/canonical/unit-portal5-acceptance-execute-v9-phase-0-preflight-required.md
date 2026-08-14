---
id: unit-portal5-acceptance-execute-v9-phase-0-preflight-required
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Phase 0 \u2014 Preflight (required)"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: tests/portal5_acceptance_v6.py
- type: code
  path: portal/platform/inference/router/app.py
- type: code
  path: portal/platform/inference/config.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.694308
updated_at: 1784946220.694308
---

Before any run, verify the environment in order. First run
`scripts/execute_preflight.py`: it prints the live production, eval, and total
workspace counts plus the persona and MCP-fleet counts from `config/portal.yaml`
and must end with "OK to run". It exits non-zero and prints a STOP banner if a
retired alias has reappeared as a workspace id, via `check_no_retired_aliases`
in the same script.

Then confirm no suite instance is already running by grepping the process table
for the entry script `tests/portal5_acceptance_v6.py`. Finally probe the
pipeline: the unauthenticated `/health` endpoint on `localhost:9099`
(registered in `portal/platform/inference/router/app.py`) returns quickly and is
the liveness gate. `PORTAL_ENABLE_EVAL` must be unset so the eval/bench
workspace set stays out of the served catalog; if the preflight flags a
retired-alias leak, stop rather than proceeding.

## Why

Acceptance runs are long and expensive, so the cheap checks happen up front. A
retired-alias leak or a second concurrent run invalidates every result that
follows, and the pipeline health probe confirms the routing surface is actually
serving before the first request. Preflight is the difference between a wasted
multi-hour run and a clean one, which is why the script prints live counts
instead of trusting a number baked into a document.
