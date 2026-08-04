---
id: unit-sec-core-capability_graph
kind: mixed
title: "Capability graph \u2014 technique coverage index"
sources:
- type: code
  path: portal/modules/security/core/capability_graph.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902828
updated_at: 1785800295.902828
---

The capability graph that indexes what the security library can cover per technique — the tool arsenal, scenarios, and oracles mapped to the ATT&CK techniques they address — and computes coverage summaries and gaps.

## Why

The graph is the answer to "what do we cover?": it maps every technique to the tools, scenarios, and oracles that address it, and the coverage summary is what surfaces the gaps. A gap engine built on the graph is what drives the growth loop — you can only grow coverage you can see.

## Interfaces

The capability graph that indexes what the security library can cover per technique — the tool arsenal, scenarios, and oracles mapped to the ATT&CK techniques they address — and computes coverage summaries and gaps lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
