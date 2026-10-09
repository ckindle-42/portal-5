---
id: unit-surface-security-review-product
kind: mixed
title: "Security review product path and analyst knowledge"
sources:
- type: code
  path: portal/modules/security/core/review/*.py
claims: []
confidence: high
tags:
- authored-v1
- security
- review
- product
created_at: 1791551882.0
updated_at: 1791551882.0
---

`portal/modules/security/core/review/` is the label-blind product path. The
public entry point is `service.run_review`: it reads a bounded window, builds
the review units, runs the deterministic pipeline and persists every result
through `verdicts.persist_run`. The service loads verdict-derived anchor cards
as of the requested time alongside the supplied static index. A new run with
learned anchors recalibrates from a recorded benign window after excluding any
unit that overlaps events used by a benign verdict anchor.

`ReviewStore` keeps concerns, append-only analyst verdicts, and learned anchors.
`service.record_verdict`, `service.queue`, and `service.contradictions` expose
the analyst loop. A `nothing` verdict adds a benign pattern, a `something`
verdict adds a confirmed finding, `unsure` adds no anchor, and a reversal
quarantines the earlier anchor. `run_review(as_of=...)` builds knowledge from
records known at that time, so a later verdict does not alter an earlier
replay. The default store is in-memory; callers may inject a store, with
durable runs and MCP exposure owned by the next task.

## Why

Analyst decisions must become reviewable knowledge without allowing machine
opinions to overwrite them. Bitemporal selection makes prior runs reproducible;
excluding benign-anchor events from the null prevents the same evidence from
teaching and calibrating the reviewer.

## Boundaries

The product stores no answer-key labels and does not execute attacks, chains,
or target operations. Verdict truth remains separate from the machine's
concern result; live detection evaluation uses bounded read-only searches.
