---
id: unit-router-workspaces
kind: mixed
title: "Router workspaces \u2014 catalog + persona tool whitelist"
sources:
- type: code
  path: portal/platform/inference/router/workspaces.py
  commit: a234187e
last_generated_commit: a234187e
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
- router
created_at: 1785798129.534917
updated_at: 1785798129.534917
---

`workspaces.py` is the routing policy's workspace catalog: `WORKSPACES`
holds one entry per user-selectable workspace with its pinned model,
per-workspace tuning knobs, and the persona map; it also resolves the tool
whitelist per workspace.

## Why

The catalog is where "what should I do" decisions are made concrete: which
model serves a workspace, what context and concurrency limits it gets,
whether it emits reasoning, and which tools its personas may call. It is
loaded from the portal config (via the workspace dict), which is what ties
the catalog to Rule 6's single source of truth — a workspace added to
`portal.yaml` appears here after sync-config, and one whose module is
disabled is excluded. The persona-to-tools resolution
(`_resolve_persona_tools`) is the authorisation boundary that decides what a
persona can call.

## Interfaces

`WORKSPACES`, `_PERSONA_MAP`, `MAX_TOOL_HOPS`, `_workspace_tools`, and
`_resolve_persona_tools` are the surface the routing and tool layers consume.

## Gotchas

`WORKSPACES` is built at import time from the config, so a config change
requires a restart to take effect — it is not re-read per request.
