---
id: unit-surface-inference
kind: mixed
title: "Inference platform layer \u2014 config single-source, tool registry, process\
  \ lifecycle"
sources:
- type: code
  path: portal/platform/inference/*.py
last_generated_commit: 9623f6b25b3e922bd0cf4b3885a926a4728b26a1
claims: []
confidence: high
tags:
- authored-v1
- platform
- inference
created_at: 1785884800.0
updated_at: 1785884800.0
---

The inference platform layer is the shared spine of the Portal 5 pipeline: the typed
`PortalConfig` over `config/portal.yaml`, the `validate_config` pre-gate that guards
the `sync_config` generators, the `ToolRegistry` that probes live MCP manifests, and
the `BackendRegistry` whose candidate cache keeps selection cheap. The
package init carries `__version__`; the launcher starts uvicorn with Prometheus
multiprocess first.

## Why

Rule 6 makes `portal.yaml` the single source of truth and every other config file a
derived artifact, which is why this layer splits into a validated model, a cheap
validator, and idempotent emitters. Tool dispatch and backend selection sit on hot
request paths, so freshness is a contract: `_candidate_cache` is invalidated inside
`_refresh_healthy_cache`, and the Prometheus multiprocess dir must exist before the
metrics client imports or workers silently corrupt shared metrics.

## Interfaces

`load_portal_config` returns the cached `PortalConfig`; `get_workspace_dict`,
`get_pipeline_mcp_servers`, and `load_persona_map` project the runtime views.
`validate_config` returns error strings without raising. `ToolRegistry` exposes
`refresh`, `get`, and `dispatch`; `BackendRegistry` exposes `get_backend_candidates`
and `health_check_all`. The `sync_config` `main` runs the idempotent emitters.

## Gotchas

Module toggles are honored in the workspace view, so a disabled module hides its
workspaces from routing. The registry probes tool servers over HTTP, so one
down at startup stays absent until a successful refresh. Unknown workspace ids clamp
to `_unknown` so the candidate cache cannot grow unbounded.
