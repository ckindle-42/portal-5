---
id: unit-tests-unit-test-wiki-search-ranking
kind: what
title: Wiki search top-hit regression gate
sources:
- type: code
  path: tests/unit/test_wiki_search_ranking.py
claims: []
confidence: high
tags:
- search
- test
- verified-v1
- wiki
created_at: 1785833000.0
updated_at: 1785833000.0
---

## What

`tests/unit/test_wiki_search_ranking.py` pins the top search hit for each of the
12 baseline queries to the value in `tests/fixtures/wiki_search_baseline.json`.
Search now ranks by keyword score plus a small kind tier (`why` 1.0, `mixed`
0.5, `what` 0.0) and a verification boost, and demotes acceptance/test-section
units by id pattern. The fixture is the gate: a query whose top hit drifts —
because a new unit outranks the pinned one, or a re-ranking changes the order —
fails the test, so search quality is checked rather than spot-checked.

## Why

The flat keyword score treated a design unit and a test-section unit
identically on equal keyword evidence, so "workspace routing" surfaced a UAT
staged-section unit ahead of the routing-design unit. The `-s\d{2}_`
id-pattern penalty and the kind tier make the design unit win the tie, and the
fixture locks the judgement so a future re-ranking cannot silently regress it.
The test is intentionally hermetic: it reads the fixture and the live store,
requiring no network or services.
