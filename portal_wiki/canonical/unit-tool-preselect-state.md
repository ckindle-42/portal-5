---
id: unit-tool-preselect-state
kind: mixed
title: "Tool preselector state \u2014 miss-driven auto-disable"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/state.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796794.296412
updated_at: 1785796794.296412
---

`state.py` tracks the preselector's per-workspace auto-disable state: when a
workspace's preselected tool subset produces a miss (the requested tool was
excluded), enough consecutive misses auto-disable preselection for that
workspace so requests fall back to the full tool set.

## Why

Preselection is only worth it when it is *correct*. If the ranker keeps
dropping the tool a user actually needs, every request becomes a miss and the
feature is actively harmful — so rather than let it keep misfiring, the
state layer accumulates the miss count and auto-disables the feature for that
workspace. This is the feedback loop that makes the feature safe to default
on incrementally: a workspace that the ranker cannot serve correctly quietly
reverts to the pre-preselect behaviour instead of degrading.

## Interfaces

`record_outcome(workspace_id, was_miss)` updates the rolling state;
`is_auto_disabled(workspace_id)` reports whether the workspace should be
bypassed; `reset(workspace_id?)` clears the state for one workspace or all.

## Gotchas

Auto-disable is per-workspace, not global — one bad workspace must not turn
off preselection for a workspace the ranker serves correctly.
