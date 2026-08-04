---
id: unit-wiki-spine-coverage-gate
kind: mixed
title: Spine code-coverage gate (portal/platform/wiki/coverage.py)
sources:
- type: code
  path: portal/platform/wiki/coverage.py
- type: code
  path: portal/platform/wiki/adapters/seed_code.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- BR
- coverage
- validate-system
- verified-v1
- wiki
created_at: 1785380311.8876002
updated_at: 1785380311.8876002
---

## What

`portal/platform/wiki/coverage.py` measures code-surface coverage for the wiki
spine: the fraction of eligible Python files cited by at least one non-aggregate
canonical unit. It is the data source for `validate_system.py`'s check **BR**
(spine code coverage ratchet).

## Why

The spine's single-write-point discipline already guarantees the forward
direction — a unit change regenerates its downstream docs. It never guaranteed
the converse: that new code arrives with a unit describing it. This module
measures the converse.

`unit-code-<subsystem>` aggregate units (auto-seeded by `adapters/seed_code.py`)
are excluded from the coverage numerator. Those units cite only the first five
files of a subsystem while titling themselves with the full file count —
counting them as coverage would grade the generator against its own output,
the same circularity the doc-generation arc paid for elsewhere.

A 100% coverage assertion is unreachable today (46/605 eligible files, 7.6%,
measured when this module landed), so the gate is a ratchet, not a cliff:
`config/spine_coverage_baseline.yaml` pins the current uncovered set, and only
growth of that set fails CI. The baseline may shrink freely as units are added.
