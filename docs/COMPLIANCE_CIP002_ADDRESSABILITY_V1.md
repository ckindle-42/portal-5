# CIP-002 Addressability — the categorisation root is addressable

**Date:** 2026-09-19 · **Task:** TASK_COMPLIANCE_DELIVER_AND_SETTLE_ENGINE_V1 §A5 · **Base:** `6ff98738`

## The decision

**The address grammar grows Attachment syntax; the register keeps carrying
Attachment structure as requirement nodes.** Decided explicitly per §A5, and
for the reason §A5 names: CIP-002 is the dependency root — it defines the
categorisation every other standard's applicability derives from, and the
sweep's `sweep_order` runs it first for exactly that reason, then reads the
other thirteen without it.

## Why not the other option

Removing the Attachment nodes would delete the register's only handle on the
impact-rating method — the very text the operator's BES Cyber System
Categorisation Process implements. The census
(`COMPLIANCE_FAMILY_CENSUS_V1`) shows the operator corpus has a real
categorisation document (47 sections in store); with the Attachment nodes
gone, that procedure would have **no requirement nodes to map against**, and
the CIP-002 hole would become permanent by construction. Growing the grammar
keeps the register, the store, and the sweep's own addressing consistent:
`requirement_nodes` already carries these ids, and
`requirement_scope.population` already resolves them — only the reading-side
address grammar refused them.

## What was measured before the change

* 26 of 33 `CIP-002-5.1a` register nodes are `Attachment 1 …` ids; `parse_ref`
  returned `None` on every one.
* The recorded family sweep skipped all 26 with *"not a regulatory address"*
  (`p7_family_sweep.json`, rows carry the error, no determination attempted).
* CIP-002-5.1a therefore contributed 0 determinations, 0 refusals — and its
  five operator sections (reachable through `R1`'s population) went unmapped,
  bucketed COVERED-BUT-UNREAD in the census.

## The change

`reading_assembly._REF_RE` gains an `Attachment N` arm with `Part N.N` /
`Section N` alternation; `Ref` carries `attachment` / `section` and
`__str__` round-trips to exactly the register's ids
(`CIP-002-5.1a Attachment 1 Part 2.3`). Nothing else moves: the fixed body is
per standard revision (an Attachment shares `NERC/CIP-002-5.1a`'s), the
population join resolves by the round-tripped node id, and the whole-standard
paths that already tolerated empty `requirement` are unchanged. Unit tests
extend `TestAddressing` with the round-trip; the parse suite passes.

## Verified live after the change

* All 33 CIP-002-5.1a nodes parse.
* `reading_material.render` on `CIP-002-5.1a Attachment 1 Part 2.3` assembles a
  20,742-char material (fixed body + the Part's own scope) — the map unit the
  sweep reads with now reaches the categorisation method.

## The owed re-run

The grammar growth re-opens CIP-002-5.1a for the sweep; the re-run happens
under this task and its receipt lands with the quality-queue work (A6).
CIP-003-8 and CIP-003-9 were never grammar-blocked — all their nodes parsed —
and stay scoped to A6.3's refusals work.
