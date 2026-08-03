---
id: unit-wiki-quality
kind: mixed
title: "Wiki quality gate \u2014 calibrated authored-unit coverage definition"
sources:
- type: code
  path: portal/platform/wiki/quality.py
  commit: 4ca84409
last_generated_commit: 4ca84409
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797332.307675
updated_at: 1785797332.307675
---

The quality module is the authored-unit gate that defines what counts as
coverage: a unit passes only if its backticked identifiers exist in the repo
(grounding), its prose clears a word floor and does not merely restate the
AST projection (substance), it carries a substantive `## Why` (structure), it
does not duplicate another unit's prose (distinctness), and every stated live
quantity is bound to a probe (claim-binding). It is the instrument behind the
coverage-100 program.

## Why

A coverage percentage is a number about nothing unless the units behind it
say something true. The gate was calibrated both directions: against the
pre-existing hand-authored corpus it must report no false rejections, and
against synthetic fakes it must catch every one. The five checks are each
chosen to stop a distinct way authorship goes hollow — grounding stops
invented symbols (the dominant failure when summarising partly-read code),
substance stops API restatement, structure demands the one thing no projection
can supply, distinctness stops template filler at scale, and claim-binding
stops a figure that will be wrong later with nothing to catch it. Claim
violations are never baselinable: a unit stating a wrong number is a bug.

## Interfaces

`assess(units)` returns the `QualityReport` of passing units and issues;
`calibrate()` runs the gate against the legacy corpus and must report 100%;
`check_grounding`, `check_substance`, `check_structure`, `check_claim_binding`,
and `check_distinctness` are the individual checks; `repo_identifiers` builds
the grounding universe.

## Gotchas

The grounding universe is the whole repo, not the cited file — a unit
legitimately names symbols it interacts with but does not define, so scoping
to cited files produced false rejections on first calibration. The authored
checks (structure floor, substance floor, claim-binding) apply only to units
tagged `authored-v1`; the legacy corpus predates the convention and is
exempt, which is itself a documented calibration decision.
