---
id: unit-wiki-provenance-ledger
kind: mixed
title: "Wiki provenance ledger \u2014 commit-recorded derivation"
sources:
- type: code
  path: portal/platform/wiki/provenance_ledger.py
  commit: 649301d0f61c5bfcf00996b57c976122dd4f8e02
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797326.372905
updated_at: 1785797326.372905
---

The provenance ledger is an append-only JSONL audit trail
(`portal_wiki/provenance_ledger.jsonl`) recording cross-run write-back
events across the episode→exec→telemetry→models chain — what happened,
when, on what evidence, with what result — distinct from the per-unit
`sources` field a `KnowledgeUnit` carries. It answers "why does the wiki
believe X" without re-deriving it from scattered result files.

(P0 A1 removed the per-unit `last_generated_commit` pin this unit used to
describe the ledger as backing; the ledger is a separate, still-live
mechanism unaffected by that removal.)

## Why

Provenance is the difference between a derived unit that is a snapshot and
one that pretends to be timeless. The ledger exists so a reader can ask "was
this write-back grounded in real evidence?" and get a durable record to
compare. It is navigation, not reverse authority — the drift census and the
quality gate decide what the current unit body should say; the ledger just
records what happened, honestly and append-only.

## Interfaces

The module provides the ledger operations (record, query, reset) over the
canonical units' provenance fields, consumed by the maintenance loop and the
drift census.

## Gotchas

A pin to a commit that does not exist (the phantom-pin failure) is exactly
the case the ledger is meant to make visible — recording a fake SHA defeats
the ledger's purpose, which is why the drift census classifies unresolvable
pins separately.
