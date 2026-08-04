---
id: unit-inference-cli-module
kind: mixed
title: "Inference CLI module \u2014 confirm-gated toggle surface"
sources:
- type: code
  path: portal/platform/inference/cli/module.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797862.900125
updated_at: 1785797862.900125
---

`portal module` is the module toggle surface: `module_list` shows every
module with its enabled state and workspace/persona/mcp counts, `module_status`
shows one module, and the enable/disable commands flip the toggle with a
confirm gate.

## Why

Module toggling is a state change on the wiki unit that is the module's
state, and a state change deserves a deliberate interface — not a hand-edited
wiki unit. The confirm gate (writing a `proposed` unit first, applying on
`--yes`) matches the write-back adapter's contract, and the counts in the
list command give an operator the blast-radius before toggling: how many
workspaces, personas, and MCP ids disappear when a module is disabled.

## Interfaces

`module_list`, `module_status`, and the enable/disable commands register on
`module_app`; the toggle writes through the module write-back path.

## Gotchas

Disabling a module hides its workspaces and routing but does not stop its
containers — the MCP servers are independent services, so the toggle is a
routing change, not a process change.
