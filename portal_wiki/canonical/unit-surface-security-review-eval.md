---
id: unit-surface-security-review-eval
kind: mixed
title: "Security review evaluation contracts"
sources:
- type: code
  path: portal/modules/security/core/review_eval/*.py
claims: []
confidence: high
tags:
- authored-v1
- security
- review
- evaluation
created_at: 1791527057.0
updated_at: 1791527057.0
---

`portal/modules/security/core/review_eval/` contains offline evaluation contracts
for the review program. `attribution` records the last stage where independently
sourced truth survived and identifies the stage with the greatest loss, breaking
ties toward the earliest stage. `decisions` parses experiment records and checks
that a record targets the binding stage, names its arms and stop rule, and is
committed before the report that resolves it. The package is the measurement
plane; it is not a product-path import.

## Interfaces

`attribution.ledger` builds stage counts from truth traces and rejects empty or
unknown-stage inputs. `attribution.by_class` and `render_markdown` group and
publish those counts. `decisions.parse` validates the record front matter, and
`decisions.problems` checks status, stage choice, report presence, and commit
ordering.

## Why

Evaluations need an explicit loss ledger because a downstream change cannot
recover truth removed earlier in the pipeline. Pre-registering decisions
prevents agents from tuning a headline score without a question, comparator,
anti-goals, or stopping rule. Keeping truth and scoring outside product code
preserves independent measurement.

## Boundaries

These contracts do not run experiments or access lab targets. Evaluation data
remains outside the review product path; the package defines how recorded truth
and pre-registered decisions are measured.
