---
id: unit-portal5-acceptance-execute-v9-coverage-current
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 Coverage (current)"
sources:
- type: code
  path: tests/acceptance/s03_routing.py
- type: code
  path: tests/acceptance/_common.py
- type: code
  path: tests/acceptance/s06_security_workspaces.py
- type: code
  path: tests/acceptance/s17_cad_render.py
- type: code
  path: scripts/execute_preflight.py
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.695499
updated_at: 1784946220.695499
---

Section S3 (a wrapper that runs S3a) covers production-workspace routing. Its
catalog is the hand-maintained `PRODUCTION_WORKSPACES` list in
`tests/acceptance/s03_routing.py`, paired with the prompt-and-signal entries in
`WORKSPACE_PROMPTS` in `tests/acceptance/_common.py`. `WORKSPACE_PROMPTS` is a
static dictionary, not derived live from `WORKSPACES`; the runtime workspace id
set is loaded separately by `_load_workspaces`, which pulls ids from the
routing layer's `WORKSPACES` mapping. The authoritative production count is
printed by `scripts/execute_preflight.py`, which reads `config/portal.yaml` and
counts workspaces whose module is not the eval module.

Section S6 covers the `auto-security` workspace and its variants, each
exercised by sending a `variant` query parameter alongside the base workspace
call. Section S17 covers `auto-cad` through its S17-10 pipeline request. The
intent is that every production workspace has routing coverage across the
sections, so run the preflight list against the section coverage and report any
production workspace that no section exercises rather than silently accepting
the gap.

## Why

Workspace coverage exists to catch routing regressions on the production
catalog, so the section set must stay aligned with `config/portal.yaml` as the
workspace list evolves. Baked counts drift exactly the way the acceptance doc's
older workspace count did, which is why the preflight prints the live
production set and the operator reconciles section coverage against it instead
of trusting a number written into prose.
