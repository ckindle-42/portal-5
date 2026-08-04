---
id: unit-tool-preselect-test-config
kind: mixed
title: "Preselector config tests \u2014 opt-in resolution contract"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/tests/test_config.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
- tests
created_at: 1785796843.193457
updated_at: 1785796843.193457
---

This test file pins the preselector's two-level config resolution: the global
flag defaults off, flips on with `PORTAL5_TOOL_PRESELECT=1`, and the
per-workspace block interacts with it correctly. All environment state is
mocked — no real config is read.

## Why

The opt-in gating is the preselector's safety mechanism, so its resolution
rules are exactly the kind of thing a refactor can quietly break. The tests
pin the default-off posture (a regression that makes the feature default on
would silently change every request path), the explicit on/off flag handling,
and the workspace-block combination — the "global on but workspace absent
means bypassed" case is the one a careless change most often gets wrong,
because it only fails for workspaces that never opted in.

## Interfaces

The suite exercises `global_preselect_enabled`, `is_preselect_enabled`,
`resolve_workspace_config`, `preselect_model`, and `default_k`, asserting
both the flag behaviour and the combined resolution.

## Gotchas

The tests clear the environment (`patch.dict(os.environ, {}, clear=True)`)
for the default-off case so a developer's own `.env` cannot accidentally
turn the feature on and fail the suite.
