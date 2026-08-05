---
id: unit-portal5-bench-sec-execute-v3-your-role
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Your Role"
sources:
- type: code
  path: portal/modules/security/core/cli.py
- type: code
  path: portal/modules/security/core/candidate_eval.py
- type: code
  path: scripts/execute_preflight.py
last_generated_commit: ace36bcf
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.706256
updated_at: 1784946220.706256
---

The execute agent's role is to run the security bench, not to build it.
Concretely: run `scripts/execute_preflight.py` and the lab readiness gate,
invoke `python3 -m portal.modules.security.core` with the flags the run
requires, diagnose failures against the code that produces them (the `cli.py`
flag definitions, `_data.py` timeout keys, `scoring.py` dimensions), retry
intelligently after correcting the invocation, and deliver the candidate
qualification report. Product code under `portal/` is read-only: a capability
failure that traces to a product bug is reported with evidence, not patched in
place. `candidate_eval.py`'s `PROMOTE_POLICY=confirm` enforces the same boundary
at the promotion step.

## Why

Splitting the executor from the implementer keeps the bench an honest
measurement instrument. If the same agent wrote the harness and then judged its
own candidates, a failing score could be "fixed" by editing the rubric; keeping
product code read-only forces capability problems to surface as findings, which
is exactly what a qualification run is supposed to produce.
