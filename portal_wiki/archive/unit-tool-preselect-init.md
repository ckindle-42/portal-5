---
id: unit-tool-preselect-init
kind: mixed
title: "Tool preselector \u2014 query-level schema narrowing, opt-in by default"
sources:
- type: code
  path: portal/platform/inference/tool_preselect/__init__.py
  commit: 50d41b55
last_generated_commit: 50d41b55
claims: []
confidence: high
tags:
- authored-v1
- platform
- tool-preselect
created_at: 1785796771.240878
updated_at: 1785796771.240878
---

The tool_preselect package implements query-level tool-schema preselection:
before a request goes to the model, a small ranker narrows the tool set to the
subset relevant to the query, so the primary model pays prefill cost for fewer
schemas. It is feature-flagged off by default and requires per-workspace
opt-in even when the global flag is on.

## Why

Full tool schemas are the dominant prefill cost on every request, and most
workspaces only ever use a handful of their tools per query. Preselection is
the answer — but it is a behavioural change to the request path, so the
two-level opt-in (global flag *and* per-workspace block) is deliberate: the
feature cannot silently change routing for a workspace that never opted in.
The package's own README is the design authority; this namespace marks the
boundary.

## Interfaces

`config` resolves the two-level opt-in, `preselector` runs the ranking
pass, `parser` turns the ranker's output into tool indices, `state` tracks
auto-disable on misses, `metrics` records outcome labels, and `cli_probe`
is the interactive probe harness.
