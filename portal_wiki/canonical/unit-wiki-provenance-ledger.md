---
id: unit-wiki-provenance-ledger
kind: mixed
title: "Wiki provenance ledger \u2014 commit-recorded derivation"
sources:
- type: code
  path: portal/platform/wiki/provenance_ledger.py
  commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
last_generated_commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797326.372905
updated_at: 1785797326.372905
---

The provenance ledger records which commit each machine-derived unit was
generated against, giving the wiki a navigation record from the canonical
body back to the code state that produced it. It is the provenance layer
behind `last_generated_commit`.

## Why

Provenance is the difference between a derived unit that is a snapshot and
one that pretends to be timeless. The ledger exists so a reader can ask "was
this unit derived from the code I am looking at?" and get a commit to
compare. It is navigation, not reverse authority — the drift census and the
quality gate decide what a stale pin *means*; the ledger just records the
pins honestly.

## Interfaces

The module provides the ledger operations (record, query, reset) over the
canonical units' provenance fields, consumed by the maintenance loop and the
drift census.

## Gotchas

A pin to a commit that does not exist (the phantom-pin failure) is exactly
the case the ledger is meant to make visible — recording a fake SHA defeats
the ledger's purpose, which is why the drift census classifies unresolvable
pins separately.
