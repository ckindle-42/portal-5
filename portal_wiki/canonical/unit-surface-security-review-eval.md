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
updated_at: 1791551211.0
---

`portal/modules/security/core/review_eval/` contains scorer-plane truth,
capture certification, folds, pre-registered arms, attribution, and validated
report contracts. `truth` derives BOTS intervals from declared entities and
sourcetypes, computes event IDs with product intake identity, and records drops
with receipts. `captures` self-tests its temporal validator before certifying
the recorded corpus. `folds` builds leave-one-family-out anchors through product
intake and checks event-ID isolation. `attribution` records the last stage where
independently sourced truth survived and identifies the greatest loss, breaking
ties toward the earliest stage. `decisions` checks that experiments target the
binding stage and are pre-registered before their resolving report. The package
is the measurement plane; product code must not import it. T3 currently keeps
`arms.DEFAULT_READER_ARM` at `no_reader`; the product's
`service.DEFAULT_READER` is `None`, so an unadopted reader leaves deterministic
review as the default.

## Interfaces

`truth.derive_bots_truth` accepts aggregate and streamed-record fetchers so the
scorer can query the real corpus without loading it into memory. Its manifest
stores intervals, counts, hashes, and product event IDs; raw events stay in
memory. `captures.derive_capture_truth` re-hashes and revalidates each admitted
capture before creating product-shaped records. `arms.ARMS` freezes the
`legacy_funnel`, installed `review_d0`, and explicit `no_reader` configurations.
`attribution.ledger`
builds stage counts from traces and rejects empty or unknown-stage inputs.
`decisions.parse` validates record front matter, and `decisions.problems` checks
status, stage choice, report presence, and commit ordering.

## Why

Evaluations need an explicit loss ledger because a downstream change cannot
recover truth removed earlier in the pipeline. Pre-registering decisions
prevents agents from tuning a headline score without a question, comparator,
anti-goals, or stopping rule. Keeping truth and scoring outside product code
preserves independent measurement.

## Boundaries

The scorer may read indexed data through injected read-only search callbacks and
may inspect the already-recorded capture corpus. It has no attack, emulation, or
target-control path. Evaluation truth remains outside the review product path;
the runner calls the public service and stores only aggregate evidence, IDs, and
hashes in reports.
