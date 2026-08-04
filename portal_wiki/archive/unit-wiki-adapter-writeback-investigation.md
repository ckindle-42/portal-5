---
id: unit-wiki-adapter-writeback-investigation
kind: mixed
title: "Wiki investigation write-back \u2014 validated-finding units"
sources:
- type: code
  path: portal/platform/wiki/adapters/writeback_investigation.py
  commit: 66aa9fda
last_generated_commit: 66aa9fda
claims: []
confidence: high
tags:
- authored-v1
- wiki
- adapter
created_at: 1785797611.736303
updated_at: 1785797611.736303
---

The investigation write-back adapter writes closed-case findings into the
wiki: each investigation finding that passed the A4-Challenger gate becomes a
MIXED unit citing the case id and its evidence ids.

## Why

The investigation layer produces findings, and only *validated* findings may
become knowledge — the adapter's contract is that unvalidated findings never
write back. Each finding is cited to its evidence, which is what keeps the
"every answer cites its source" property true for investigation-derived
units: a finding is only as trustworthy as the evidence it cites, so the
citation is part of the unit, not an afterthought.

## Interfaces

`writeback_investigation_findings(case_id, findings, auto_confirm)` returns
the written units.

## Gotchas

The A4-Challenger gate is the admission criterion — a finding that did not
pass challenger validation is deliberately excluded, because writing it back
would fabricate support the finding never earned.
