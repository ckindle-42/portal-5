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

---

## What

`tests/unit/test_wiki_search_ranking.py` checks the Phase 7 defect directly:
`wiki_search("workspace routing")` must put `unit-surface-router` first and
must not place `unit-acceptance-s03_routing` in the top two. Search ranks by
keyword score plus a small kind tier and a verification boost, and demotes
acceptance/test-section units by id pattern.

## Why

The flat keyword score treated a design unit and a test-section unit
identically on equal keyword evidence, so "workspace routing" surfaced a UAT
staged-section unit ahead of the routing-design unit. The `-s\d{2}_`
id-pattern penalty and the kind tier make the design unit win the tie. The
remaining test calls the live store with that one query and reads the order
back; it takes no network and no service.
