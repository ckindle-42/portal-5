---
id: unit-user-guide-workspaces
kind: what
title: "USER_GUIDE \u2014 Workspaces"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/sync_config.py
- type: code
  path: portal/platform/inference/router/workspaces.py
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.513955
updated_at: 1784946220.513955
---

Workspaces are the routing layer. Each workspace defined in `config/portal.yaml`
declares a `name`, a `model_hint` that selects its model, `expose_to_owui`
(whether it becomes an Open WebUI preset), a tool list, and optional `variants`.
The synchronization script writes presets only for exposed workspaces, so the
model dropdown shows that curated set; variants such as the agentic coding lanes
or the security sub-roles (`blueteam`, `redteam`) are addressed by query hint, not
listed in the dropdown. `auto-video` is defined but `expose_to_owui: false` and
shelved, and `auto-council` runs an opt-in multi-model review chain whose quorum
and dissent handling are enforced in code.

## Why

The guide presented a fixed table of dropdown workspaces that mixed exposed
workspaces, hidden variants, a shelved service, and a persona that never existed
in config. Workspace presence in the interface is a mechanical consequence of
`expose_to_owui` in `portal.yaml` plus the preset generator, so the unit must
describe that rule instead of reprinting a snapshot. This keeps the claim stable
as workspaces are added or shelved.
