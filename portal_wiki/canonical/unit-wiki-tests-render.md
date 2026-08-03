---
id: unit-wiki-tests-render
kind: mixed
title: "Wiki render tests \u2014 HUMAN-OWNED awareness + report contract"
sources:
- type: code
  path: portal/platform/wiki/tests/test_render.py
  commit: dfa74e2e
last_generated_commit: dfa74e2e
claims: []
confidence: high
tags:
- authored-v1
- wiki
- tests
created_at: 1785795461.8825479
updated_at: 1785795461.8825479
---

This test file pins down the render module's two hard-won contracts: that a
`WIKI:GENERATED` block sitting *outside* a `WIKI:HUMAN-OWNED` region is
detected, and that `render_report` returns the migration-coverage figures the
AW gate consumes. The first contract is the fence-everything loophole closer:
if a doc wraps every generated block in a human-owned fence, the block is
effectively unmanaged, and this test guards the function that finds exactly
those blocks.

## Why

The HUMAN-OWNED fence was introduced as a deliberate escape hatch for prose a
human owns outright, and the loophole this test closes is using it to hide
*generated* content from the migration gate. `_find_unit_ids_outside_human_owned`
is the instrument that tells the gate which blocks are genuinely managed, and
these cases pin its boundary: markers alone, markers inside a fence, mixed
documents, and none at all. The render-report tests pin the numeric contract
(`migrated`, `unmigrated`, `blocks_total`, `coverage_pct`) that AW compares
against live unit bodies — a change to that dict shape fails here before it
can break the validate harness.

## Interfaces

`_find_unit_ids_outside_human_owned(text)` returns the unit ids of generated
blocks not enclosed in a human-owned region; `render_report(tmp_path)` reads a
repo-root and returns the migration report dict. The tests exercise both
against synthetic doc text in `tmp_path` fixtures, never against the live
tree.

## Gotchas

The human-owned exclusion is purely positional (marker nesting), not semantic
— a block that is *inside* a fence but logically should be generated is still
excluded, which is why the fence requires a `reason` on newer fences.
