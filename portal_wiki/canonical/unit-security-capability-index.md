---
id: unit-security-capability-index
kind: mixed
title: "Security capability index \u2014 read-only arsenal query surface"
sources:
- type: code
  path: portal/modules/security/core/capability/__init__.py
  commit: b0aa6770
claims: []
confidence: high
tags:
- authored-v1
- module
- security
- capability
created_at: 1785795017.817317
updated_at: 1785795017.817317
---

The capability subpackage makes the security library legible to the decide
step: it indexes what already exists — the tool arsenal, service probes,
challenge classes, lab targets, oracles, and field-journal priors — into one
queryable index, and renders that index for humans. It is strictly read-only
over the engagement machinery.

## Why

The decide step needs to know what the library can do *before* it picks an
action, and before the capability index existed that answer required reading
several heterogeneous registries by hand. Indexing them once into a uniform
shape is the difference between a decider that can ask "what tools serve this
service?" and one that must re-implement registry traversal. The read-only
constraint is deliberate: an index that mutated the arsenal while querying it
would make the decision surface itself a side effect.

## Interfaces

`build_index()` and `query()` come from `index`; `load_tool_catalog()`,
`tools_for_service()`, `tools_for_phase()`, and `verify_tools_present()` come
from `tool_inventory`; and `render_capabilities()` / `render_tool_arsenal()`
from `render`. The `__init__` re-exports all of them so consumers import from
the capability package rather than reaching into the submodule internals.
