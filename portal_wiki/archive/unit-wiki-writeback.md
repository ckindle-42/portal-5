---
id: unit-wiki-writeback
kind: mixed
title: "Wiki writeback \u2014 propose/confirm bridge into canonical"
sources:
- type: code
  path: portal/platform/wiki/writeback.py
  commit: 4ca84409
last_generated_commit: 4ca84409
claims: []
confidence: high
tags:
- authored-v1
- wiki
created_at: 1785797311.298802
updated_at: 1785797311.298802
---

The writeback module is the growth-loop's bridge into the wiki: proposed
units from an agent or a detection loop land in a proposed directory, are
listed, and can be confirmed into the canonical store. It is what makes the
self-improving cycle (gap → propose → prove → confirm → cited unit) possible.

## Why

The wiki must not accept arbitrary proposed content as canonical — that would
make the spine a dumping ground. The propose/confirm split is the gate: a
detection or an agent writes a proposal to the proposed directory, where it
is inspectable, and only an explicit `confirm_unit` promotes it into the
canonical store with its citations intact. The directory redirect
(`set_proposed_dir`) keeps the mechanism testable without touching the real
proposed or canonical trees.

## Interfaces

`list_proposed` and `reset_proposed_dir` manage the proposal inbox;
`confirm_unit` promotes a proposal to canonical; the module is consumed by
the growth loop's `_writeback_proven_detection` and by the integration test
that proves the full cycle.

## Gotchas

A confirmed unit carries its citations — the writeback path is what keeps the
"every answer cites its source" contract true for machine-generated units, so
confirming must preserve `sources`, not strip them.
