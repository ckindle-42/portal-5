---
id: unit-DESIGN_WIKI-section-granularity
kind: why
title: Section-level default granularity, fact-atom only for reuse or volatility
sources:
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
claims: []
confidence: high
tags:
- design
- granularity
- verified-v1
- wiki
created_at: 1784941411.445164
updated_at: 1784941411.445164
---

A unit maps by default to a doc section -- the chunk a human or agent thinks of as the thing they edit. Finer fact-unit decomposition is reserved for values that earn it: a value reused across more than one doc, or a value independently volatile on its own schedule, such as counts, ports, model IDs, or thresholds. Rationale is the tiebreaker between the two; the aim is the unit best for an agent to manage and easiest for a human to read. Pure fact-atomization of everything is forbidden, because it turns a doc into a flood of unreadable micro-units and is worse for both audiences.

The `seed_facts.py` derivers implement this through the `_make_unit` idempotency pattern: when the newly derived body matches what is already stored, the prior unit's sources and timestamps are reused wholesale, so a unit file changes on disk only when its body actually changed. (Before P0 A1, a `last_generated_commit` pin was reused the same way and this paragraph described it; P0 deleted the pin outright, so the idempotency now governs sources/timestamps only.) A body change lands in a single commit — repeated `sync-config` runs with no body change produce no churn either way.

## Why

Granularity is a management choice, not a data-model property, so the rule exists to stop the cheapest failure mode: machine-seeded authors splitting everything into atoms and flooding the canonical directory with near-duplicate noise. The `_make_unit` pattern exists for the parallel reason -- if the stamp advanced on every run, every fact-unit would be rewritten on every `sync-config`, turning an idempotent render step into a permanent diff generator and making HEAD pinning meaningless.
