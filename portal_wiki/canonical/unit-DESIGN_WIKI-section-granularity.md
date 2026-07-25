---
id: unit-DESIGN_WIKI-section-granularity
kind: why
title: Section-level default granularity, fact-atom only for reuse or volatility
sources:
- type: design
  path: docs/DESIGN_WIKI_GENERATION_LOOP_V1.md
  commit: d869257b
  section: '3'
- type: code
  path: portal/platform/wiki/adapters/seed_facts.py
  commit: d869257b
last_generated_commit: d869257b
confidence: high
tags:
- design
- wiki
- granularity
created_at: 1784941411.445164
updated_at: 1784941411.445164
---

A unit maps to a **doc section** -- the chunk a human/agent thinks of as "the thing I edit." This is the default granularity. Decompose to a finer fact-unit **only** when a value is:

- **(i) Reused** across more than one doc, or
- **(ii) Independently volatile** (counts, ports, model IDs, thresholds).

Rationale is the tiebreaker: best for the agent to manage, easiest for the human to read. **Pure fact-atomization of everything is forbidden** -- it produces hundreds of unreadable micro-units, worse for both audiences.

The existing `seed_facts.py` derivers follow the `_make_unit` idempotent pattern: they only advance `last_generated_commit` when the body actually changes, preventing no-op churn on every `sync-config` run.
