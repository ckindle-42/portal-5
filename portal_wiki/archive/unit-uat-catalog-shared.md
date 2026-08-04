---
id: unit-uat-catalog-shared
kind: mixed
title: "UAT catalog shared \u2014 assertion + refusal vocabulary"
sources:
- type: code
  path: tests/uat_catalog/_shared.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785799956.0302951
updated_at: 1785799956.0302951
---

`_shared.py` holds the shared definitions the catalog groups import: the
assertion sets (`_CC01_ASSERTIONS`, `_CC01_ASSERTIONS_BENCH`) and the
`REFUSAL_PHRASES` re-export, so each group module declares what it needs
without duplicating the vocabulary.

## Why

The catalog groups share assertion and refusal vocabulary, and duplicating
it per group would let the groups drift — one group checking a refusal
phrase another does not. The shared module is the single source for the
assertion sets, so a change to an assertion or a refusal phrase applies to
every group that imports it.

## Interfaces

`_CC01_ASSERTIONS`, `_CC01_ASSERTIONS_BENCH`, and `REFUSAL_PHRASES`.

## Gotchas

The assertion sets are the contract the group tests are graded against — a
change here changes what every group's tests assert.
