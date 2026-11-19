---
id: unit-DESIGN_WIKI-section-granularity
kind: why
title: Section-level default granularity, fact-atom only for reuse or volatility
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
claims:
- probe: repo.path.exists
  path: portal/platform/wiki/adapters/seed_facts.py
  equals: true
confidence: high
tags:
- design
- granularity
- verified-v1
- wiki
---

A unit maps by default to a doc section -- the chunk a human or agent thinks of as the thing they edit. Finer fact-unit decomposition is reserved for values that earn it: a value reused across more than one doc, or a value independently volatile on its own schedule, such as counts, ports, model IDs, or thresholds. Rationale is the tiebreaker between the two; the aim is the unit best for an agent to manage and easiest for a human to read. Pure fact-atomization of everything is forbidden, because it turns a doc into a flood of unreadable micro-units and is worse for both audiences.

The `seed_facts.py` derivers build fact units in memory when the wiki MCP is queried. No generated fact-unit files, timestamps, or sync step are needed; each response reflects its current config, code, or probe inputs.

## Why

Granularity is a management choice, not a data-model property. Durable guidance belongs in readable authored units; volatile values belong in reusable computed fact units, which stay out of the canonical directory and are resolved when requested.
