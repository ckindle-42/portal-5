---
id: unit-tool-preselect-config
kind: mixed
title: "Tool preselector config \u2014 two-level opt-in resolution"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/config.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796777.02047
updated_at: 1785796777.02047
---

`config.py` resolves the two levels of opt-in for the tool preselector: the
global `PORTAL5_TOOL_PRESELECT` flag (default off) and the per-workspace
`tool_preselect:` block in `config/portal.yaml`. Both must be present for the
feature to activate on a request.

## Why

Two-level gating is a safety design, not bureaucracy. The global flag lets an
operator disable the feature everywhere at once (a regressed ranker cannot be
forced on any workspace), while the per-workspace block is the workspace
owner's explicit consent — a workspace that never opted in is bypassed even
with the global flag on. That ordering (global first, workspace second) is
what keeps a default-off feature from being accidentally activated by a
one-line config edit in the wrong file.

## Interfaces

`global_preselect_enabled()` reads the env flag; `WorkspacePreselectConfig`
is the frozen dataclass of resolved settings (enabled, k, confidence_floor);
`resolve_workspace_config` combines the flag and the workspace block into the
effective configuration. `DEFAULT_PRESELECT_MODEL` names the ranker model.

## Gotchas

`k` (how many tools to keep) and the confidence floor both come from the
workspace block, so two workspaces may legitimately preselect with different
aggressiveness on the same global flag.
