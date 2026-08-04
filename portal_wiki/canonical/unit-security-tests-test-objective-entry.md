---
id: unit-security-tests-test-objective-entry
kind: what
title: Objective-mode emergent entry gate tests
sources:
- type: code
  path: portal/modules/security/tests/test_objective_entry.py
last_generated_commit: baca992c674a3cbb36a619e8f62e7e88b8fccfff
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5
updated_at: 1784946220.5
---

`test_objective_entry.py` gates the emergent, objective-mode entry path without ever editing the platform run loop. Fake provider, executor, and perception pairs let the suite drive `derive_max_iterations`, `run_with_no_progress_halt`, and `run_emergent_engagement` directly against scripted outcomes. The derived iteration budget is grounded in the longest matching procedure, hard-capped by `HARD_MAX_ITERATIONS`, and floored at a single slack when nothing matches. A no-progress halt stops a stagnant run early with a blocked outcome while genuine progress runs to the budget, and an empty provider short-circuits before any execution. The `PORTAL_EMERGENT` flag decides whether the path stays inert or builds an unseeded `EngagementGoal`, threads the domain hint and an initial perception seed into the provider query, retires unbound live capabilities, and rejects empty target lists.

## Why

The platform run loop is shared infrastructure, so new objective-mode behaviour must live in its own wrapper rather than as edits to that loop. Testing the wrapper directly with fakes keeps the harness honest about its own invariants — the derived budget, the no-progress halt, and the perception seed were all live-verification findings — while leaving the shared loop untouched and the harness bounded to a single responsibility.
